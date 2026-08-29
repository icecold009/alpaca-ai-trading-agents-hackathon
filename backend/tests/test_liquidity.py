from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from riskcourt.domain import OptionQuote, OptionRight
from riskcourt.liquidity import (
    ContractSnapshot,
    ContractStatus,
    assess_contract_liquidity,
)

AS_OF = datetime(2026, 8, 29, 12, tzinfo=UTC)


def snapshot(
    *,
    bid: str = "3.10",
    ask: str = "3.20",
    quoted_at: datetime = AS_OF,
    expiry: date = date(2026, 9, 18),
    status: ContractStatus = ContractStatus.ACTIVE,
    tradable: bool = True,
    delta: Decimal | None = Decimal("0.45"),
) -> ContractSnapshot:
    expiry_code = expiry.strftime("%y%m%d")
    return ContractSnapshot(
        quote=OptionQuote(
            occ_symbol=f"SPY{expiry_code}C00600000",
            underlying_symbol="SPY",
            expiry=expiry,
            strike=Decimal("600"),
            right=OptionRight.CALL,
            evidence_id="ev_liquidity",
            bid=Decimal(bid),
            ask=Decimal(ask),
            quoted_at=quoted_at,
        ),
        status=status,
        tradable=tradable,
        delta=delta,
    )


def test_supported_contract_passes_all_filters() -> None:
    result = assess_contract_liquidity(snapshot(), AS_OF)

    assert result.passed is True
    assert result.reasons == ()
    assert result.days_to_expiry == 20


def test_illiquid_contract_is_rejected() -> None:
    result = assess_contract_liquidity(snapshot(bid="1", ask="2"), AS_OF)

    assert result.passed is False
    assert "spread_too_wide" in result.reasons


def test_crossed_quote_is_rejected_by_the_domain_contract() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to bid"):
        snapshot(bid="3.20", ask="3.10")


def test_stale_quote_is_rejected() -> None:
    result = assess_contract_liquidity(
        snapshot(quoted_at=AS_OF - timedelta(seconds=31)),
        AS_OF,
    )

    assert "quote_stale_or_future_dated" in result.reasons


def test_missing_greek_is_rejected() -> None:
    result = assess_contract_liquidity(snapshot(delta=None), AS_OF)

    assert "missing_greeks" in result.reasons


def test_zero_dte_contract_is_rejected() -> None:
    result = assess_contract_liquidity(snapshot(expiry=AS_OF.date()), AS_OF)

    assert result.days_to_expiry == 0
    assert "unsupported_expiry" in result.reasons


def test_unsupported_contract_status_is_rejected() -> None:
    result = assess_contract_liquidity(snapshot(status=ContractStatus.INACTIVE), AS_OF)

    assert "unsupported_contract" in result.reasons
