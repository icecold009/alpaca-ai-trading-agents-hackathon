from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from riskcourt.domain import OptionQuote, OptionRight
from riskcourt.option_hurdle import calculate_vertical_debit_spread

EXPIRY = date(2026, 9, 18)
QUOTED_AT = datetime(2026, 8, 29, 12, tzinfo=UTC)


def quote(
    occ_symbol: str,
    strike: str,
    right: OptionRight,
    bid: str,
    ask: str,
    evidence_id: str,
) -> OptionQuote:
    return OptionQuote(
        occ_symbol=occ_symbol,
        underlying_symbol="SPY",
        expiry=EXPIRY,
        strike=Decimal(strike),
        right=right,
        evidence_id=evidence_id,
        bid=Decimal(bid),
        ask=Decimal(ask),
        quoted_at=QUOTED_AT,
    )


def test_hand_worked_call_debit_spread_geometry() -> None:
    geometry = calculate_vertical_debit_spread(
        quote("SPY260918C00600000", "600", OptionRight.CALL, "3.10", "3.20", "ev_call_600"),
        quote("SPY260918C00605000", "605", OptionRight.CALL, "1.70", "1.80", "ev_call_605"),
    )

    assert geometry.net_debit == Decimal("1.50")
    assert geometry.spread_width == Decimal("5")
    assert geometry.break_even_underlying == Decimal("601.50")
    assert geometry.option_implied_hurdle == Decimal("0.30")
    assert geometry.maximum_loss == Decimal("150.00")


def test_hand_worked_put_debit_spread_geometry() -> None:
    geometry = calculate_vertical_debit_spread(
        quote("SPY260918P00600000", "600", OptionRight.PUT, "3.90", "4.00", "ev_put_600"),
        quote("SPY260918P00595000", "595", OptionRight.PUT, "1.50", "1.60", "ev_put_595"),
    )

    assert geometry.net_debit == Decimal("2.50")
    assert geometry.spread_width == Decimal("5")
    assert geometry.break_even_underlying == Decimal("597.50")
    assert geometry.option_implied_hurdle == Decimal("0.50")
    assert geometry.maximum_loss == Decimal("250.00")


def test_zero_quote_is_rejected() -> None:
    with pytest.raises(ValueError, match="nonzero bid and ask"):
        calculate_vertical_debit_spread(
            quote("SPY260918C00600000", "600", OptionRight.CALL, "0", "3.20", "ev_call_600"),
            quote("SPY260918C00605000", "605", OptionRight.CALL, "1.70", "1.80", "ev_call_605"),
        )


def test_invalid_leg_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="long strike below"):
        calculate_vertical_debit_spread(
            quote("SPY260918C00605000", "605", OptionRight.CALL, "1.70", "1.80", "ev_call_605"),
            quote("SPY260918C00600000", "600", OptionRight.CALL, "3.10", "3.20", "ev_call_600"),
        )
