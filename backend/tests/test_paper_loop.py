from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from riskcourt.alpaca_account import (
    AccountSnapshot,
    MarketClockSnapshot,
    PaperAccountState,
)
from riskcourt.alpaca_market_data import UnderlyingMarketState, UnderlyingQuote
from riskcourt.alpaca_option_chain import ChainContract, OptionChainState
from riskcourt.alpaca_order import AlpacaOrderAdapter
from riskcourt.domain import (
    DecisionEvent,
    DecisionEventType,
    EvidenceItem,
    EvidenceType,
    ExecutionStatus,
    OptionRight,
)
from riskcourt.event_store import AppendOnlyDecisionLog, PersistentDecisionLog
from riskcourt.jurors import DeterministicJurorStub
from riskcourt.model_provider import ProviderBoundary, ProviderUnavailable
from riskcourt.paper_loop import (
    PaperCycleDependencies,
    record_filled_pnl,
    run_paper_cycle,
)
from riskcourt.risk_limits import PortfolioRiskSnapshot, RiskStateStore

NOW = datetime(2026, 8, 30, 15, 0, tzinfo=UTC)


class FakeAccount:
    def __init__(self, state: PaperAccountState) -> None:
        self.state = state

    def fetch(self) -> PaperAccountState:
        return self.state


class FakeMarket:
    def __init__(self, state: UnderlyingMarketState) -> None:
        self.state = state

    def fetch(self, *, symbol: str, now: datetime) -> UnderlyingMarketState:
        return self.state


class FakeChain:
    def __init__(self, state: OptionChainState) -> None:
        self.state = state

    def fetch(self, underlying_symbol: str, **_: object) -> OptionChainState:
        return self.state


class FakeClient:
    def __init__(self, *, status: str = "new") -> None:
        self.calls = 0
        self.status = status

    def submit_order(self, request: object) -> object:
        self.calls += 1
        client_order_id = request.client_order_id  # type: ignore[attr-defined]
        return SimpleNamespace(
            client_order_id=client_order_id,
            status=self.status,
            submitted_at=NOW,
            updated_at=NOW,
            filled_qty="0",
            filled_avg_price=None,
            filled_at=None,
            replaced_by=None,
        )


def account(*, market_open: bool = True, level: int = 3) -> PaperAccountState:
    return PaperAccountState(
        fetched_at=NOW,
        account=AccountSnapshot(
            observed_at=NOW,
            status="ACTIVE",
            equity=Decimal("100000"),
            options_buying_power=Decimal("100000"),
            options_approved_level=level,
            options_trading_level=level,
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
        ),
        clock=MarketClockSnapshot(
            timestamp=NOW,
            is_open=market_open,
            next_open=NOW + timedelta(hours=1),
            next_close=NOW + timedelta(hours=6),
        ),
        positions=(),
        pending_orders=(),
    )


def market() -> UnderlyingMarketState:
    return UnderlyingMarketState(
        fetched_at=NOW,
        quote=UnderlyingQuote(
            symbol="SPY",
            feed="iex",
            quoted_at=NOW,
            bid=Decimal("640"),
            ask=Decimal("640.01"),
            bid_size=Decimal("100"),
            ask_size=Decimal("100"),
            stale=False,
        ),
        bars=(),
    )


def chain() -> OptionChainState:
    def contract(strike: str) -> ChainContract:
        expiry = date(2026, 9, 11)
        return ChainContract(
            occ_symbol=f"SPY260911C{int(Decimal(strike) * 1000):08d}",
            underlying_symbol="SPY",
            expiry=expiry,
            strike=Decimal(strike),
            right=OptionRight.CALL,
            feed="indicative",
            quoted_at=NOW,
            bid=Decimal("1.00"),
            ask=Decimal("1.10"),
            implied_volatility=Decimal("0.2"),
            delta=Decimal("0.5"),
            gamma=Decimal("0.1"),
            theta=Decimal("-0.1"),
            vega=Decimal("0.2"),
            missing_values=(),
        )

    return OptionChainState(
        underlying_symbol="SPY",
        feed="indicative",
        expiration_from=NOW.date(),
        expiration_to=date(2026, 9, 20),
        strike_from=Decimal("630"),
        strike_to=Decimal("650"),
        contracts=(contract("640"), contract("641")),
    )


def dependencies(
    *, account_state: PaperAccountState | None = None, client: FakeClient | None = None
) -> tuple[PaperCycleDependencies, AppendOnlyDecisionLog, FakeClient]:
    resolved_client = client or FakeClient()
    log = AppendOnlyDecisionLog("case_live_test")
    risk = RiskStateStore(
        PortfolioRiskSnapshot(
            account_equity=Decimal("100000"),
            open_options_risk=Decimal("0"),
            open_option_positions=0,
            pending_option_orders=0,
            daily_pnl=Decimal("0"),
            kill_switch_enabled=False,
            revision=0,
        )
    )
    return (
        PaperCycleDependencies(
            account=FakeAccount(account_state or account()),  # type: ignore[arg-type]
            market=FakeMarket(market()),  # type: ignore[arg-type]
            chain=FakeChain(chain()),  # type: ignore[arg-type]
            orders=AlpacaOrderAdapter(resolved_client),
            provider=ProviderBoundary(DeterministicJurorStub()),
            risk=risk,
            event_log=log,
        ),
        log,
        resolved_client,
    )


def test_paper_cycle_submits_one_order_and_records_audit_chain() -> None:
    deps, log, client = dependencies()

    result = run_paper_cycle(deps, case_id="case_live_test", now=NOW)

    assert result.status == "submitted"
    assert result.order_attempted is True
    assert result.execution is not None
    assert result.execution.status is ExecutionStatus.SUBMITTED
    assert result.lifecycle is not None
    assert result.lifecycle.status is ExecutionStatus.SUBMITTED
    assert client.calls == 1
    assert [item.event.event_type for item in log.events] == [
        DecisionEventType.CASE_OPENED,
        DecisionEventType.FORECAST_RECORDED,
        DecisionEventType.INTENT_PROPOSED,
        DecisionEventType.RISK_EVALUATED,
        DecisionEventType.APPROVAL_ISSUED,
        DecisionEventType.EXECUTION_UPDATED,
    ]
    log.verify()


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (account(market_open=False), "market_closed"),
        (account(level=2), "options_trading_level_unavailable"),
    ],
)
def test_paper_cycle_blocks_before_any_market_or_order_call(
    state: PaperAccountState, reason: str
) -> None:
    deps, _, client = dependencies(account_state=state)

    result = run_paper_cycle(deps, case_id="case_live_test", now=NOW)

    assert (result.status, result.reason) == ("blocked", reason)
    assert result.order_attempted is False
    assert client.calls == 0


def test_paper_cycle_provider_failure_abstains_without_order() -> None:
    deps, _, client = dependencies()

    class BrokenProvider:
        def call(self, *_: object, **__: object) -> object:
            raise ProviderUnavailable("timeout")

    deps = replace(deps, provider=BrokenProvider())  # type: ignore[arg-type]
    result = run_paper_cycle(deps, case_id="case_live_test", now=NOW)

    assert (result.status, result.reason) == ("abstained", "timeout")
    assert client.calls == 0


def test_filled_pnl_snapshot_is_dollar_based_and_hash_logged() -> None:
    deps, log, _ = dependencies()
    result = run_paper_cycle(deps, case_id="case_live_test", now=NOW)
    assert result.execution is not None
    assert result.verdict is not None
    filled = result.execution.model_copy(
        update={
            "status": ExecutionStatus.FILLED,
            "filled_at": NOW,
            "filled_debit": Decimal("0.10"),
        }
    )
    filled_result = replace(result, execution=filled)

    snapshot = record_filled_pnl(
        filled_result,
        event_log=log,
        position_value=Decimal("15"),
    )

    assert snapshot.cost_basis == Decimal("10")
    assert snapshot.unrealized_pnl == Decimal("5")
    assert log.events[-1].event.event_type is DecisionEventType.PNL_RECORDED
    log.verify()


def test_persistent_log_recovers_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "events.json"
    first = PersistentDecisionLog("case_live_test", path)
    evidence = EvidenceItem(
        evidence_id="evidence_test",
        evidence_type=EvidenceType.POLICY,
        source="test",
        symbol="SPY",
        observed_at=NOW,
        payload_sha256="0" * 64,
        summary="test",
        raw_reference="test",
    )
    first.append(
        DecisionEvent(
            event_id="event_test",
            case_id="case_live_test",
            sequence=0,
            event_type=DecisionEventType.CASE_OPENED,
            occurred_at=NOW,
            evidence_ids=(evidence.evidence_id,),
            payload={"mode": "paper"},
        )
    )
    second = PersistentDecisionLog("case_live_test", path)
    assert len(second.events) == 1
    second.verify()
