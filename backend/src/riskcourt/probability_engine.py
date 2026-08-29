"""Deterministic aggregation for independent, evidence-bound juror forecasts."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from riskcourt.domain import ProbabilityForecast
from riskcourt.strategy_math import ZERO, calibrated_probability


class AggregationStatus(StrEnum):
    READY = "ready"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class JurorContribution:
    juror_id: str
    calibrated_probability: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class JuryAggregate:
    status: AggregationStatus
    probability: Decimal | None
    contributions: tuple[JurorContribution, ...]
    total_weight: Decimal
    disagreement: Decimal | None
    reason: str | None


def aggregate_forecasts(
    forecasts: tuple[ProbabilityForecast, ...],
    expected_jurors: tuple[str, ...],
    maximum_disagreement: Decimal = Decimal("0.20"),
) -> JuryAggregate:
    """Aggregate a complete jury or return an explicit deterministic abstention."""

    if not ZERO <= maximum_disagreement <= Decimal("1"):
        raise ValueError("maximum_disagreement must be between 0 and 1")
    if not expected_jurors or len(set(expected_jurors)) != len(expected_jurors):
        raise ValueError("expected_jurors must contain unique juror IDs")

    forecasts_by_juror = {forecast.juror_id: forecast for forecast in forecasts}
    if len(forecasts_by_juror) != len(forecasts):
        raise ValueError("a jury cannot contain duplicate juror forecasts")
    if set(forecasts_by_juror) != set(expected_jurors):
        return JuryAggregate(
            status=AggregationStatus.ABSTAIN,
            probability=None,
            contributions=(),
            total_weight=ZERO,
            disagreement=None,
            reason="juror_set_incomplete",
        )

    first = forecasts[0]
    if any(
        forecast.case_id != first.case_id
        or forecast.outcome is not first.outcome
        or forecast.horizon_at != first.horizon_at
        for forecast in forecasts[1:]
    ):
        raise ValueError("juror forecasts must target the same case, outcome, and horizon")

    contributions = tuple(
        JurorContribution(
            juror_id=juror_id,
            calibrated_probability=calibrated_probability(
                forecasts_by_juror[juror_id].probability,
                forecasts_by_juror[juror_id].calibration_score,
            ),
            weight=(
                forecasts_by_juror[juror_id].calibration_score
                * forecasts_by_juror[juror_id].confidence_stake
            ),
        )
        for juror_id in expected_jurors
    )
    total_weight = sum((item.weight for item in contributions), start=ZERO)
    if total_weight == ZERO:
        return JuryAggregate(
            status=AggregationStatus.ABSTAIN,
            probability=None,
            contributions=contributions,
            total_weight=ZERO,
            disagreement=None,
            reason="zero_jury_weight",
        )

    probability = (
        sum(
            (item.calibrated_probability * item.weight for item in contributions),
            start=ZERO,
        )
        / total_weight
    )
    calibrated_values = [item.calibrated_probability for item in contributions]
    disagreement = max(calibrated_values) - min(calibrated_values)
    if disagreement > maximum_disagreement:
        return JuryAggregate(
            status=AggregationStatus.ABSTAIN,
            probability=probability,
            contributions=contributions,
            total_weight=total_weight,
            disagreement=disagreement,
            reason="juror_disagreement",
        )

    return JuryAggregate(
        status=AggregationStatus.READY,
        probability=probability,
        contributions=contributions,
        total_weight=total_weight,
        disagreement=disagreement,
        reason=None,
    )
