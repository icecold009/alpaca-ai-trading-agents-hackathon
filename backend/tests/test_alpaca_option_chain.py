from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from riskcourt.alpaca_option_chain import (
    AlpacaOptionChainAdapter,
    OptionChainState,
    OptionChainUnavailable,
)


class FakeClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    def get_option_chain(self, request_params: object) -> dict[str, object]:
        return self.response


def snapshot(*, quote: bool = True, greeks: bool = True) -> object:
    return SimpleNamespace(
        latest_quote=(
            SimpleNamespace(
                timestamp=datetime(2026, 9, 1, tzinfo=UTC),
                bid_price=1.2,
                ask_price=1.3,
            )
            if quote
            else None
        ),
        implied_volatility=0.22 if greeks else None,
        greeks=(
            SimpleNamespace(delta=0.5, gamma=0.02, theta=-0.1, vega=0.3)
            if greeks
            else None
        ),
    )


def fetch(client: FakeClient) -> OptionChainState:
    return AlpacaOptionChainAdapter(client).fetch(
        "SPY",
        expiration_from=date(2026, 9, 4),
        expiration_to=date(2026, 9, 18),
        strike_from=Decimal("630"),
        strike_to=Decimal("650"),
    )


def test_chain_is_deterministic_and_parses_calls_and_puts() -> None:
    state = fetch(
        FakeClient(
            {
                "SPY260918P00640000": snapshot(),
                "SPY260904C00635000": snapshot(),
            }
        )
    )
    assert [item.occ_symbol for item in state.contracts] == [
        "SPY260904C00635000",
        "SPY260918P00640000",
    ]
    assert state.contracts[1].strike == Decimal("640")
    assert state.contracts[1].right.value == "put"


def test_missing_quote_iv_and_greeks_are_explained() -> None:
    state = fetch(FakeClient({"SPY260918C00640000": snapshot(quote=False, greeks=False)}))
    assert state.contracts[0].missing_values == ("quote", "implied_volatility", "greeks")
    assert state.contracts[0].bid is None


def test_empty_chain_is_rejected() -> None:
    with pytest.raises(OptionChainUnavailable, match="chain empty"):
        fetch(FakeClient({}))


def test_invalid_occ_symbol_is_rejected() -> None:
    with pytest.raises(OptionChainUnavailable, match="invalid option symbol"):
        fetch(FakeClient({"AAPL260918C00640000": snapshot()}))
