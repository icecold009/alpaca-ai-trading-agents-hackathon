from decimal import Decimal

import pytest

from riskcourt.domain import OptionRight
from riskcourt.edge_policy import EdgeDecision, evaluate_probability_edge
from riskcourt.option_hurdle import VerticalSpreadGeometry
from riskcourt.probability_engine import AggregationStatus, JuryAggregate


def jury(probability: str) -> JuryAggregate:
    return JuryAggregate(
        status=AggregationStatus.READY,
        probability=Decimal(probability),
        contributions=(),
        total_weight=Decimal("1"),
        disagreement=Decimal("0"),
        reason=None,
    )


def geometry() -> VerticalSpreadGeometry:
    return VerticalSpreadGeometry(
        underlying_symbol="SPY",
        expiry="2026-09-18",
        right=OptionRight.CALL,
        long_occ_symbol="SPY260918C00600000",
        short_occ_symbol="SPY260918C00605000",
        net_debit=Decimal("1.50"),
        spread_width=Decimal("5"),
        break_even_underlying=Decimal("601.50"),
        option_implied_hurdle=Decimal("0.32"),
        maximum_loss=Decimal("150"),
    )


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        ("0.399", EdgeDecision.ABSTAIN),
        ("0.400", EdgeDecision.PASS),
        ("0.401", EdgeDecision.PASS),
    ],
)
def test_below_equal_and_above_threshold(
    probability: str,
    expected: EdgeDecision,
) -> None:
    result = evaluate_probability_edge(jury(probability), geometry(), Decimal("0.08"))

    assert result.decision is expected


def test_non_ready_jury_abstains_before_edge_calculation() -> None:
    unavailable_jury = JuryAggregate(
        status=AggregationStatus.ABSTAIN,
        probability=None,
        contributions=(),
        total_weight=Decimal("0"),
        disagreement=None,
        reason="juror_set_incomplete",
    )

    result = evaluate_probability_edge(unavailable_jury, geometry(), Decimal("0.08"))

    assert result.decision is EdgeDecision.ABSTAIN
    assert result.probability_edge is None
    assert result.reason == "juror_set_incomplete"
