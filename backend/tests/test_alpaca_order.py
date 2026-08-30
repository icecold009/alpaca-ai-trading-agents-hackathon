from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from alpaca.trading.enums import PositionIntent

from riskcourt.alpaca_option_chain import ChainContract, OptionChainState
from riskcourt.alpaca_order import AlpacaOrderAdapter
from riskcourt.domain import OptionRight
from riskcourt.spread_selector import SpreadCandidate, select_vertical_spreads

NOW = datetime(2026, 8, 30, 15, 0, tzinfo=UTC)


def candidate() -> SpreadCandidate:
    def c(strike: str) -> ChainContract:
        return ChainContract(
            occ_symbol=f"SPY260911C{int(Decimal(strike) * 1000):08d}",
            underlying_symbol="SPY",
            expiry=date(2026, 9, 11),
            strike=Decimal(strike),
            right=OptionRight.CALL,
            feed="indicative",
            quoted_at=NOW,
            bid=Decimal("1.00"),
            ask=Decimal("1.10"),
            implied_volatility=Decimal(".2"),
            delta=Decimal(".5"),
            gamma=Decimal(".1"),
            theta=Decimal("-.1"),
            vega=Decimal(".2"),
            missing_values=(),
        )

    state = OptionChainState(
        underlying_symbol="SPY",
        feed="indicative",
        expiration_from=date(2026, 9, 4),
        expiration_to=date(2026, 9, 18),
        strike_from=Decimal("630"),
        strike_to=Decimal("650"),
        contracts=(c("640"), c("641")),
    )
    return select_vertical_spreads(state, as_of=NOW)[0]


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def submit_order(self, order_data: object) -> object:
        self.calls += 1
        return SimpleNamespace(id="paper-order")


def test_build_maps_one_contract_day_mleg_with_position_intents() -> None:
    request = AlpacaOrderAdapter.build_vertical_order(candidate(), client_order_id="riskcourt-001")
    fields = request.to_request_fields()

    assert fields["qty"] == 1
    assert fields["order_class"] == "mleg"
    assert fields["time_in_force"] == "day"
    assert fields["limit_price"] == pytest.approx(0.1)
    assert [leg["position_intent"] for leg in fields["legs"]] == [
        PositionIntent.BUY_TO_OPEN.value,
        PositionIntent.SELL_TO_OPEN.value,
    ]


def test_rejects_unsafe_price_and_requires_approval() -> None:
    with pytest.raises(ValueError, match="no greater"):
        AlpacaOrderAdapter.build_vertical_order(
            candidate(), client_order_id="riskcourt-001", limit_price=Decimal("2")
        )
    adapter = AlpacaOrderAdapter(FakeClient())
    request = adapter.build_vertical_order(candidate(), client_order_id="riskcourt-001")
    with pytest.raises(PermissionError, match="explicit approval"):
        adapter.submit(request)


def test_duplicate_request_is_replayed_without_second_submission() -> None:
    client = FakeClient()
    adapter = AlpacaOrderAdapter(client)
    request = adapter.build_vertical_order(candidate(), client_order_id="riskcourt-001")

    first = adapter.submit(request, approved=True)
    second = adapter.submit(request, approved=True)

    assert first.action.value == "submit"
    assert second.action.value == "replay"
    assert client.calls == 1


def test_exit_maps_close_intents_to_a_credit_order() -> None:
    request = AlpacaOrderAdapter.build_vertical_exit_order(
        candidate(), client_order_id="riskcourt-exit-001", credit_price=Decimal("0.50")
    )
    fields = request.to_request_fields()

    assert fields["limit_price"] == pytest.approx(-0.5)
    assert [leg["position_intent"] for leg in fields["legs"]] == [
        "sell_to_close",
        "buy_to_close",
    ]
