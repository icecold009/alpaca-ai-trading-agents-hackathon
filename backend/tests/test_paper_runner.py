from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from riskcourt.alpaca_account import (
    AccountSnapshot,
    MarketClockSnapshot,
    PaperAccountState,
    PendingOrderSnapshot,
    PositionSnapshot,
)
from riskcourt.paper_runner import (
    build_risk_state,
    load_provider_client,
    sanitize_result,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def account_state(*, positions: tuple[PositionSnapshot, ...] = ()) -> PaperAccountState:
    return PaperAccountState(
        fetched_at=NOW,
        account=AccountSnapshot(
            observed_at=NOW,
            status="ACTIVE",
            equity=Decimal("100000"),
            options_buying_power=Decimal("50000"),
            options_approved_level=3,
            options_trading_level=3,
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
        ),
        clock=MarketClockSnapshot(
            timestamp=NOW,
            is_open=True,
            next_open=NOW + timedelta(hours=1),
            next_close=NOW + timedelta(hours=6),
        ),
        positions=positions,
        pending_orders=(),
    )


class ProviderFactory:
    def complete(self, request: object) -> object:
        raise AssertionError("test provider must not be called")


def test_load_provider_client_supports_module_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    module = SimpleNamespace(factory=ProviderFactory)
    monkeypatch.setitem(__import__("sys").modules, "test_provider_module", module)

    client = load_provider_client("test_provider_module:factory")

    assert type(client).__name__ == "ProviderFactory"


@pytest.mark.parametrize(
    "spec", [None, "", "missing", "missing:factory", "test_provider_module:nope"]
)
def test_load_provider_client_rejects_missing_or_invalid_specs(spec: str | None) -> None:
    with pytest.raises((ValueError, ImportError, AttributeError, TypeError)):
        load_provider_client(spec)


def test_build_risk_state_fails_closed_when_existing_option_risk_is_unknown() -> None:
    option_position = PositionSnapshot(
        symbol="SPY260911C00640000",
        asset_class="us_option",
        quantity=Decimal("1"),
        side="long",
        market_value=Decimal("100"),
        unrealized_pl=Decimal("0"),
    )

    with pytest.raises(ValueError, match="existing option risk"):
        build_risk_state(account_state(positions=(option_position,)), daily_pnl=Decimal("0"))


def test_build_risk_state_preserves_pending_option_order_count() -> None:
    state = account_state()
    state = state.model_copy(
        update={
            "pending_orders": (
                PendingOrderSnapshot(
                    client_order_id="riskcourt-test",
                    symbol=None,
                    status="accepted",
                    order_class="mleg",
                    submitted_at=NOW,
                ),
            )
        }
    )

    risk = build_risk_state(state, daily_pnl=Decimal("-10"))

    assert risk.authorize_execution(Decimal("100")).passed is False


def test_sanitize_result_removes_order_reference_and_keeps_status() -> None:
    result = SimpleNamespace(
        case_id="case_runner",
        status="submitted",
        reason="paper_order_submitted",
        order_attempted=True,
        account=account_state(),
        market=None,
        chain=None,
        execution=SimpleNamespace(
            status=SimpleNamespace(value="accepted"),
            client_order_id="riskcourt-secret-order-id",
        ),
        lifecycle=SimpleNamespace(status=SimpleNamespace(value="accepted")),
        pnl_snapshot=None,
    )

    summary = sanitize_result(result)

    assert summary == {
        "case_id": "case_runner",
        "status": "submitted",
        "reason": "paper_order_submitted",
        "order_attempted": True,
        "account": account_state().sanitized_summary(),
        "market": None,
        "chain": None,
        "execution_status": "accepted",
        "lifecycle_status": "accepted",
        "pnl": None,
    }
    assert "riskcourt-secret-order-id" not in str(summary)
