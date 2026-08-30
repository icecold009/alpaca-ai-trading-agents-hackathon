"""Deterministic jury orchestration with abstention on every partial failure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from riskcourt.domain import ForecastOutcome, ProbabilityForecast
from riskcourt.edge_policy import EdgeDecision, EdgeVerdict, evaluate_probability_edge
from riskcourt.jurors import JUROR_SPECS, JurorSpec, run_juror
from riskcourt.model_provider import ProviderBoundary, ProviderUnavailable
from riskcourt.option_hurdle import VerticalSpreadGeometry
from riskcourt.probability_engine import AggregationStatus, JuryAggregate, aggregate_forecasts


@dataclass(frozen=True, slots=True)
class JuryDecision:
    forecasts: tuple[ProbabilityForecast, ...]
    aggregate: JuryAggregate
    edge: EdgeVerdict | None
    decision: EdgeDecision
    reason: str


def run_jury(
    boundary: ProviderBoundary,
    geometry: VerticalSpreadGeometry,
    *,
    case_id: str,
    outcome: ForecastOutcome,
    produced_at: datetime,
    horizon_at: datetime,
    evidence_ids: tuple[str, ...],
    specs: tuple[JurorSpec, ...] = JUROR_SPECS,
    minimum_edge: Decimal = Decimal("0.08"),
) -> JuryDecision:
    forecasts: list[ProbabilityForecast] = []
    try:
        for spec in specs:
            forecasts.append(
                run_juror(
                    boundary,
                    spec,
                    case_id=case_id,
                    outcome=outcome,
                    produced_at=produced_at,
                    horizon_at=horizon_at,
                    available_evidence_ids=evidence_ids,
                )
            )
    except (ProviderUnavailable, ValueError) as error:
        empty = JuryAggregate(
            status=AggregationStatus.ABSTAIN,
            probability=None,
            contributions=(),
            total_weight=Decimal("0"),
            disagreement=None,
            reason="provider_failure",
        )
        return JuryDecision(tuple(forecasts), empty, None, EdgeDecision.ABSTAIN, str(error))

    aggregate = aggregate_forecasts(tuple(forecasts), tuple(spec.juror_id for spec in specs))
    edge = evaluate_probability_edge(aggregate, geometry, minimum_edge)
    return JuryDecision(tuple(forecasts), aggregate, edge, edge.decision, edge.reason)
