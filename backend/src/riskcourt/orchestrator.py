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
from riskcourt.typesafe_state import NO_SUPPORTED_EVIDENCE, TypeSafeState


@dataclass(frozen=True, slots=True)
class JuryDecision:
    forecasts: tuple[ProbabilityForecast, ...]
    aggregate: JuryAggregate
    edge: EdgeVerdict | None
    decision: EdgeDecision
    reason: str
    abstentions: tuple[tuple[str, str], ...] = ()


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
    minimum_quorum: int = 2,
    minimum_edge: Decimal = Decimal("0.08"),
    state: TypeSafeState | None = None,
) -> JuryDecision:
    if minimum_quorum < 1:
        raise ValueError("minimum juror quorum must be positive")
    forecasts: list[ProbabilityForecast] = []
    active_specs: list[JurorSpec] = []
    abstentions: list[tuple[str, str]] = []
    try:
        for spec in specs:
            if state is not None and not state.for_juror(spec.juror_id).evidence:
                abstentions.append((spec.juror_id, NO_SUPPORTED_EVIDENCE))
                continue
            try:
                forecast = run_juror(
                    boundary,
                    spec,
                    case_id=case_id,
                    outcome=outcome,
                    produced_at=produced_at,
                    horizon_at=horizon_at,
                    available_evidence_ids=evidence_ids,
                    state=state,
                )
            except ProviderUnavailable as error:
                reason = str(error)
                if reason in {NO_SUPPORTED_EVIDENCE, "low_evidence_quality"}:
                    abstentions.append((spec.juror_id, reason))
                    continue
                raise
            forecasts.append(forecast)
            active_specs.append(spec)
    except (ProviderUnavailable, ValueError) as error:
        empty = JuryAggregate(
            status=AggregationStatus.ABSTAIN,
            probability=None,
            contributions=(),
            total_weight=Decimal("0"),
            disagreement=None,
            reason="provider_failure",
        )
        return JuryDecision(
            tuple(forecasts),
            empty,
            None,
            EdgeDecision.ABSTAIN,
            str(error),
            tuple(abstentions),
        )

    if not active_specs:
        empty = JuryAggregate(
            status=AggregationStatus.ABSTAIN,
            probability=None,
            contributions=(),
            total_weight=Decimal("0"),
            disagreement=None,
            reason=NO_SUPPORTED_EVIDENCE,
        )
        return JuryDecision(
            tuple(forecasts),
            empty,
            None,
            EdgeDecision.ABSTAIN,
            NO_SUPPORTED_EVIDENCE,
            tuple(abstentions),
        )

    if len(active_specs) < minimum_quorum:
        empty = JuryAggregate(
            status=AggregationStatus.ABSTAIN,
            probability=None,
            contributions=(),
            total_weight=Decimal("0"),
            disagreement=None,
            reason="insufficient_juror_quorum",
        )
        return JuryDecision(
            tuple(forecasts),
            empty,
            None,
            EdgeDecision.ABSTAIN,
            "insufficient_juror_quorum",
            tuple(abstentions),
        )

    aggregate = aggregate_forecasts(
        tuple(forecasts), tuple(spec.juror_id for spec in active_specs)
    )
    edge = evaluate_probability_edge(aggregate, geometry, minimum_edge)
    return JuryDecision(
        tuple(forecasts), aggregate, edge, edge.decision, edge.reason, tuple(abstentions)
    )
