from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.settings import RuntimeMode, Settings


class Value(StrEnum):
    ACTIVE = "ACTIVE"
    OPTION = "us_option"
    LONG = "long"
    ACCEPTED = "accepted"
    SIMPLE = "simple"


class FakeClient:
    def __init__(self) -> None:
        now = datetime(2026, 8, 29, 15, 0, tzinfo=UTC)
        self.account = SimpleNamespace(
            status=Value.ACTIVE,
            equity="100000.00",
            options_buying_power="50000.00",
            options_approved_level=3,
            options_trading_level=3,
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
        )
        self.clock = SimpleNamespace(
            timestamp=now,
            is_open=False,
            next_open=now + timedelta(days=2),
            next_close=now + timedelta(days=2, hours=6, minutes=30),
        )
        self.positions: list[object] = [
            SimpleNamespace(
                symbol="SPY260918C00650000",
                asset_class=Value.OPTION,
                qty="1",
                side=Value.LONG,
                market_value="125.00",
                unrealized_pl="5.00",
            )
        ]
        self.orders: list[object] = [
            SimpleNamespace(
                client_order_id="riskcourt-case-001",
                symbol="SPY260918C00650000",
                status=Value.ACCEPTED,
                order_class=Value.SIMPLE,
                submitted_at=now,
            )
        ]
        self.order_filter: object | None = None

    def get_account(self) -> object:
        return self.account

    def get_clock(self) -> object:
        return self.clock

    def get_all_positions(self) -> list[object]:
        return self.positions

    def get_orders(self, filter: object = None) -> list[object]:
        self.order_filter = filter
        return self.orders


def test_adapter_translates_account_clock_positions_and_open_orders() -> None:
    client = FakeClient()
    state = AlpacaAccountAdapter(client).fetch()

    assert state.account.equity == 100000
    assert state.account.options_buying_power == 50000
    assert state.account.options_trading_level == 3
    assert state.clock.is_open is False
    assert state.positions[0].symbol == "SPY260918C00650000"
    assert state.pending_orders[0].client_order_id == "riskcourt-case-001"
    assert client.order_filter is not None


def test_sanitized_summary_omits_balances_order_references_and_symbols() -> None:
    summary = AlpacaAccountAdapter(FakeClient()).fetch().sanitized_summary()
    rendered = str(summary)

    assert summary["equity_present"] is True
    assert summary["position_count"] == 1
    assert "100000" not in rendered
    assert "riskcourt-case-001" not in rendered
    assert "SPY260918C00650000" not in rendered


def test_adapter_rejects_untyped_raw_lists() -> None:
    client = FakeClient()
    client.positions = {"positions": []}  # type: ignore[assignment]

    with pytest.raises(TypeError, match="typed position and order lists"):
        AlpacaAccountAdapter(client).fetch()


def test_factory_requires_paper_mode() -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        alpaca_api_key_id=SecretStr("unused"),
        alpaca_api_secret_key=SecretStr("unused"),
    )

    with pytest.raises(ValueError, match="paper mode"):
        AlpacaAccountAdapter.from_settings(settings)
