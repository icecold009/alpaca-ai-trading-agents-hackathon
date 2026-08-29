"""Deterministic option-contract liquidity and freshness filters."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from riskcourt.domain import OptionQuote


class ContractStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class ContractSnapshot:
    quote: OptionQuote
    status: ContractStatus
    tradable: bool
    delta: Decimal | None


@dataclass(frozen=True, slots=True)
class LiquidityVerdict:
    passed: bool
    reasons: tuple[str, ...]
    relative_spread: Decimal | None
    days_to_expiry: int


def assess_contract_liquidity(
    snapshot: ContractSnapshot,
    as_of: datetime,
    maximum_quote_age: timedelta = timedelta(seconds=30),
    maximum_relative_spread: Decimal = Decimal("0.20"),
    minimum_days_to_expiry: int = 7,
    maximum_days_to_expiry: int = 21,
) -> LiquidityVerdict:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if maximum_quote_age <= timedelta(0):
        raise ValueError("maximum_quote_age must be positive")
    if not Decimal("0") <= maximum_relative_spread <= Decimal("1"):
        raise ValueError("maximum_relative_spread must be between 0 and 1")
    if minimum_days_to_expiry < 1 or maximum_days_to_expiry < minimum_days_to_expiry:
        raise ValueError("expiry window must be positive and ordered")

    quote = snapshot.quote
    reasons: list[str] = []
    relative_spread: Decimal | None = None
    if quote.bid <= 0 or quote.ask <= 0:
        reasons.append("zero_bid_or_ask")
    else:
        midpoint = (quote.bid + quote.ask) / Decimal("2")
        relative_spread = (quote.ask - quote.bid) / midpoint
        if relative_spread > maximum_relative_spread:
            reasons.append("spread_too_wide")

    quote_age = as_of - quote.quoted_at
    if quote_age < timedelta(0) or quote_age > maximum_quote_age:
        reasons.append("quote_stale_or_future_dated")

    days_to_expiry = (quote.expiry - as_of.date()).days
    if not minimum_days_to_expiry <= days_to_expiry <= maximum_days_to_expiry:
        reasons.append("unsupported_expiry")
    if snapshot.status is not ContractStatus.ACTIVE or not snapshot.tradable:
        reasons.append("unsupported_contract")
    if snapshot.delta is None:
        reasons.append("missing_greeks")

    return LiquidityVerdict(
        passed=not reasons,
        reasons=tuple(reasons),
        relative_spread=relative_spread,
        days_to_expiry=days_to_expiry,
    )
