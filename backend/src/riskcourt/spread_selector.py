"""Deterministic selection of liquid, defined-risk vertical debit spreads."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

from riskcourt.alpaca_option_chain import ChainContract, OptionChainState
from riskcourt.domain import OptionQuote, OptionRight
from riskcourt.liquidity import ContractSnapshot, ContractStatus, assess_contract_liquidity
from riskcourt.option_hurdle import VerticalSpreadGeometry, calculate_vertical_debit_spread


class SpreadCandidate:
    """A reconstructable candidate and the quote evidence used to select it."""

    __slots__ = ("geometry", "long_contract", "short_contract")

    def __init__(
        self,
        geometry: VerticalSpreadGeometry,
        long_contract: ChainContract,
        short_contract: ChainContract,
    ) -> None:
        self.geometry = geometry
        self.long_contract = long_contract
        self.short_contract = short_contract


def select_vertical_spreads(
    chain: OptionChainState,
    *,
    as_of: datetime,
    supported_widths: tuple[Decimal, ...] = (
        Decimal("1"),
        Decimal("2"),
        Decimal("5"),
        Decimal("10"),
    ),
    maximum_quote_age: timedelta = timedelta(seconds=30),
    maximum_relative_spread: Decimal = Decimal("0.20"),
) -> tuple[SpreadCandidate, ...]:
    """Return candidates ordered by expiry, width, right, and strikes."""

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if not supported_widths or any(width <= 0 for width in supported_widths):
        raise ValueError("supported widths must be positive")

    eligible = [
        contract
        for contract in chain.contracts
        if _liquid(contract, chain, as_of, maximum_quote_age, maximum_relative_spread)
    ]
    candidates: list[SpreadCandidate] = []
    for long_contract in eligible:
        for short_contract in eligible:
            if not _valid_pair(long_contract, short_contract, supported_widths):
                continue
            try:
                geometry = calculate_vertical_debit_spread(
                    _quote(long_contract), _quote(short_contract)
                )
            except ValueError:
                continue
            candidates.append(SpreadCandidate(geometry, long_contract, short_contract))
    candidates.sort(
        key=lambda candidate: (
            candidate.long_contract.expiry,
            candidate.geometry.spread_width,
            candidate.geometry.right.value,
            candidate.long_contract.strike,
            candidate.short_contract.strike,
        )
    )
    return tuple(candidates)


def _liquid(
    contract: ChainContract,
    chain: OptionChainState,
    as_of: datetime,
    maximum_quote_age: timedelta,
    maximum_relative_spread: Decimal,
) -> bool:
    if contract.quoted_at is None or contract.bid is None or contract.ask is None:
        return False
    if contract.underlying_symbol != chain.underlying_symbol:
        return False
    quote = _quote(contract)
    verdict = assess_contract_liquidity(
        ContractSnapshot(
            quote=quote,
            status=ContractStatus.ACTIVE,
            tradable=True,
            delta=contract.delta,
        ),
        as_of,
        maximum_quote_age=maximum_quote_age,
        maximum_relative_spread=maximum_relative_spread,
    )
    return verdict.passed


def _valid_pair(
    long_contract: ChainContract, short_contract: ChainContract, widths: tuple[Decimal, ...]
) -> bool:
    if long_contract.occ_symbol == short_contract.occ_symbol:
        return False
    if long_contract.underlying_symbol != short_contract.underlying_symbol:
        return False
    if (
        long_contract.expiry != short_contract.expiry
        or long_contract.right is not short_contract.right
    ):
        return False
    width = abs(long_contract.strike - short_contract.strike)
    if width not in widths:
        return False
    if long_contract.right is OptionRight.CALL:
        return long_contract.strike < short_contract.strike
    return long_contract.strike > short_contract.strike


def _quote(contract: ChainContract) -> OptionQuote:
    if contract.bid is None or contract.ask is None or contract.quoted_at is None:
        raise ValueError("candidate quote is incomplete")
    evidence_id = "quote-" + hashlib.sha256(contract.occ_symbol.encode()).hexdigest()[:16]
    return OptionQuote(
        evidence_id=evidence_id,
        occ_symbol=contract.occ_symbol,
        underlying_symbol=contract.underlying_symbol,
        expiry=contract.expiry,
        strike=contract.strike,
        right=contract.right,
        bid=contract.bid,
        ask=contract.ask,
        quoted_at=contract.quoted_at,
    )
