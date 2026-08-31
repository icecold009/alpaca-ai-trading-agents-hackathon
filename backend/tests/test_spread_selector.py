from datetime import UTC, date, datetime
from decimal import Decimal

from riskcourt.alpaca_option_chain import ChainContract, OptionChainState
from riskcourt.domain import OptionRight
from riskcourt.spread_selector import select_vertical_spreads

NOW = datetime(2026, 8, 30, 15, 0, tzinfo=UTC)


def contract(strike: str, right: OptionRight, *, expiry: date = date(2026, 9, 11)) -> ChainContract:
    prefix = f"SPY{expiry.strftime('%y%m%d')}{'C' if right is OptionRight.CALL else 'P'}"
    symbol = prefix + f"{int(Decimal(strike) * 1000):08d}"
    return ChainContract(
        occ_symbol=symbol,
        underlying_symbol="SPY",
        expiry=expiry,
        strike=Decimal(strike),
        right=right,
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


def chain(*contracts: ChainContract) -> OptionChainState:
    return OptionChainState(
        underlying_symbol="SPY",
        feed="indicative",
        expiration_from=date(2026, 9, 4),
        expiration_to=date(2026, 9, 18),
        strike_from=Decimal("620"),
        strike_to=Decimal("660"),
        contracts=contracts,
    )


def test_selector_orders_only_supported_same_expiry_verticals() -> None:
    state = chain(
        contract("640", OptionRight.CALL),
        contract("641", OptionRight.CALL),
        contract("645", OptionRight.CALL),
        contract("640", OptionRight.PUT),
        contract("639", OptionRight.PUT),
    )
    candidates = select_vertical_spreads(state, as_of=NOW)

    assert [(item.geometry.right, item.geometry.spread_width) for item in candidates] == [
        (OptionRight.CALL, Decimal("1")),
        (OptionRight.PUT, Decimal("1")),
        (OptionRight.CALL, Decimal("5")),
    ]
    assert all(item.geometry.maximum_loss > 0 for item in candidates)
    assert all(item.geometry.break_even_underlying > 0 for item in candidates)


def test_stale_and_missing_quote_contracts_are_excluded() -> None:
    stale = contract("640", OptionRight.CALL).model_copy(
        update={"quoted_at": datetime(2026, 8, 30, 14, 0, tzinfo=UTC)}
    )
    missing = contract("641", OptionRight.CALL).model_copy(update={"bid": None})
    assert select_vertical_spreads(chain(stale, missing), as_of=NOW) == ()


def test_crossed_option_quotes_are_excluded_without_raising() -> None:
    crossed = contract("640", OptionRight.CALL).model_copy(
        update={"bid": Decimal("1.20"), "ask": Decimal("1.10")}
    )
    valid_short = contract("641", OptionRight.CALL)

    assert select_vertical_spreads(chain(crossed, valid_short), as_of=NOW) == ()
