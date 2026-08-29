from decimal import Decimal

import pytest

from riskcourt.strategy_math import (
    JurorEstimate,
    calculate_edge,
    defined_risk_contracts,
    maximum_loss_per_contract,
)


def test_hand_calculated_probability_edge_fixture() -> None:
    estimates = (
        JurorEstimate(Decimal("0.62"), Decimal("0.9"), Decimal("0.8")),
        JurorEstimate(Decimal("0.58"), Decimal("0.8"), Decimal("0.7")),
        JurorEstimate(Decimal("0.54"), Decimal("0.7"), Decimal("0.6")),
    )

    edge = calculate_edge(
        estimates=estimates,
        net_debit=Decimal("1.50"),
        spread_width=Decimal("5.00"),
        slippage_buffer=Decimal("0.10"),
        minimum_edge=Decimal("0.08"),
    )
    maximum_loss = maximum_loss_per_contract(Decimal("1.50"))
    contracts = defined_risk_contracts(Decimal("100000"), maximum_loss)

    assert edge.jury_probability == Decimal("0.5737411764705882352941176471")
    assert edge.market_hurdle == Decimal("0.32")
    assert edge.probability_edge == Decimal("0.2537411764705882352941176471")
    assert edge.clears_threshold is True
    assert maximum_loss == Decimal("150.00")
    assert contracts == 1


def test_contract_sizing_abstains_when_one_contract_exceeds_budget() -> None:
    assert defined_risk_contracts(Decimal("100000"), Decimal("501")) == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"net_debit": Decimal("0")}, "net_debit must be positive"),
        ({"spread_width": Decimal("0")}, "spread_width must be positive"),
        ({"slippage_buffer": Decimal("-0.01")}, "cannot be negative"),
        ({"net_debit": Decimal("5"), "slippage_buffer": Decimal("0.01")}, "cannot exceed"),
    ],
)
def test_invalid_edge_geometry_is_rejected(
    overrides: dict[str, Decimal],
    message: str,
) -> None:
    values = {
        "net_debit": Decimal("1.50"),
        "spread_width": Decimal("5.00"),
        "slippage_buffer": Decimal("0.10"),
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=message):
        calculate_edge(
            estimates=(JurorEstimate(Decimal("0.60"), Decimal("0.90"), Decimal("0.80")),),
            minimum_edge=Decimal("0.08"),
            **values,
        )
