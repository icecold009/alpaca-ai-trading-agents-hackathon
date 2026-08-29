"""Entry edge policy that converts jury and market odds into pass or abstain."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from riskcourt.option_hurdle import VerticalSpreadGeometry
from riskcourt.probability_engine import AggregationStatus, JuryAggregate


class EdgeDecision(StrEnum):
    PASS = "pass"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class EdgeVerdict:
    decision: EdgeDecision
    jury_probability: Decimal | None
    market_hurdle: Decimal
    probability_edge: Decimal | None
    minimum_edge: Decimal
    reason: str


def evaluate_probability_edge(
    jury: JuryAggregate,
    geometry: VerticalSpreadGeometry,
    minimum_edge: Decimal,
) -> EdgeVerdict:
    if not Decimal("0") <= minimum_edge <= Decimal("1"):
        raise ValueError("minimum_edge must be between 0 and 1")
    if jury.status is not AggregationStatus.READY or jury.probability is None:
        return EdgeVerdict(
            decision=EdgeDecision.ABSTAIN,
            jury_probability=jury.probability,
            market_hurdle=geometry.option_implied_hurdle,
            probability_edge=None,
            minimum_edge=minimum_edge,
            reason=jury.reason or "jury_not_ready",
        )

    edge = jury.probability - geometry.option_implied_hurdle
    if edge < minimum_edge:
        return EdgeVerdict(
            decision=EdgeDecision.ABSTAIN,
            jury_probability=jury.probability,
            market_hurdle=geometry.option_implied_hurdle,
            probability_edge=edge,
            minimum_edge=minimum_edge,
            reason="insufficient_probability_edge",
        )
    return EdgeVerdict(
        decision=EdgeDecision.PASS,
        jury_probability=jury.probability,
        market_hurdle=geometry.option_implied_hurdle,
        probability_edge=edge,
        minimum_edge=minimum_edge,
        reason="minimum_probability_edge_cleared",
    )
