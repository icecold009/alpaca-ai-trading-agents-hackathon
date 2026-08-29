"""Deterministic payoff geometry for vertical debit-spread candidates."""

from dataclasses import dataclass
from decimal import Decimal

from riskcourt.domain import OptionQuote, OptionRight
from riskcourt.strategy_math import maximum_loss_per_contract, option_implied_hurdle


@dataclass(frozen=True, slots=True)
class VerticalSpreadGeometry:
    underlying_symbol: str
    expiry: str
    right: OptionRight
    long_occ_symbol: str
    short_occ_symbol: str
    net_debit: Decimal
    spread_width: Decimal
    break_even_underlying: Decimal
    option_implied_hurdle: Decimal
    maximum_loss: Decimal


def calculate_vertical_debit_spread(
    long_quote: OptionQuote,
    short_quote: OptionQuote,
    slippage_buffer: Decimal = Decimal("0"),
) -> VerticalSpreadGeometry:
    """Build a same-expiry call or put debit spread from executable quote sides."""

    if (
        long_quote.underlying_symbol != short_quote.underlying_symbol
        or long_quote.expiry != short_quote.expiry
        or long_quote.right is not short_quote.right
    ):
        raise ValueError("vertical spread legs must share underlying, expiry, and option right")
    if min(long_quote.bid, long_quote.ask, short_quote.bid, short_quote.ask) <= 0:
        raise ValueError("vertical spread quotes must have nonzero bid and ask")

    if long_quote.right is OptionRight.CALL:
        if long_quote.strike >= short_quote.strike:
            raise ValueError("call debit spread requires the long strike below the short strike")
        spread_width = short_quote.strike - long_quote.strike
        break_even_base = long_quote.strike
        break_even_sign = Decimal("1")
    else:
        if long_quote.strike <= short_quote.strike:
            raise ValueError("put debit spread requires the long strike above the short strike")
        spread_width = long_quote.strike - short_quote.strike
        break_even_base = long_quote.strike
        break_even_sign = Decimal("-1")

    net_debit = long_quote.ask - short_quote.bid
    hurdle = option_implied_hurdle(net_debit, spread_width, slippage_buffer)
    return VerticalSpreadGeometry(
        underlying_symbol=long_quote.underlying_symbol,
        expiry=long_quote.expiry.isoformat(),
        right=long_quote.right,
        long_occ_symbol=long_quote.occ_symbol,
        short_occ_symbol=short_quote.occ_symbol,
        net_debit=net_debit,
        spread_width=spread_width,
        break_even_underlying=break_even_base + break_even_sign * net_debit,
        option_implied_hurdle=hurdle,
        maximum_loss=maximum_loss_per_contract(net_debit),
    )
