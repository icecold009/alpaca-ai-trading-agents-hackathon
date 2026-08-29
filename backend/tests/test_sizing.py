from decimal import Decimal

import pytest

from riskcourt.domain import OptionRight
from riskcourt.option_hurdle import VerticalSpreadGeometry
from riskcourt.sizing import SizingDecision, size_defined_risk_position


def geometry(maximum_loss: str) -> VerticalSpreadGeometry:
    return VerticalSpreadGeometry(
        underlying_symbol="SPY",
        expiry="2026-09-18",
        right=OptionRight.CALL,
        long_occ_symbol="SPY260918C00600000",
        short_occ_symbol="SPY260918C00605000",
        net_debit=Decimal(maximum_loss) / Decimal("100"),
        spread_width=Decimal("5"),
        break_even_underlying=Decimal("600") + Decimal(maximum_loss) / Decimal("100"),
        option_implied_hurdle=Decimal(maximum_loss) / Decimal("500"),
        maximum_loss=Decimal(maximum_loss),
    )


def test_exact_half_percent_boundary_allows_one_contract() -> None:
    result = size_defined_risk_position(
        Decimal("100000"),
        geometry("500.00"),
        requested_quantity=1,
    )

    assert result.decision is SizingDecision.APPROVE
    assert result.risk_budget == Decimal("500.000")
    assert result.approved_quantity == 1
    assert result.approved_maximum_loss == Decimal("500.00")


def test_one_cent_over_boundary_vetoes() -> None:
    result = size_defined_risk_position(
        Decimal("100000"),
        geometry("500.01"),
        requested_quantity=1,
    )

    assert result.decision is SizingDecision.VETO
    assert result.approved_quantity == 0


def test_requested_multi_contract_position_resizes_to_one() -> None:
    result = size_defined_risk_position(
        Decimal("100000"),
        geometry("150"),
        requested_quantity=3,
    )

    assert result.decision is SizingDecision.RESIZE
    assert result.approved_quantity == 1
    assert result.approved_maximum_loss == Decimal("150")


def test_fractional_option_quantity_is_rejected() -> None:
    with pytest.raises(ValueError, match="whole number of contracts"):
        size_defined_risk_position(
            Decimal("100000"),
            geometry("150"),
            requested_quantity=1.5,  # type: ignore[arg-type]
        )
