from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from riskcourt.domain import ForecastOutcome, ProbabilityForecast
from riskcourt.probability_engine import AggregationStatus, aggregate_forecasts

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)
EXPECTED_JURORS = ("juror_market", "juror_catalyst", "juror_volatility")


def forecast(
    juror_id: str,
    probability: Decimal | str,
    calibration: Decimal | str = "1",
    stake: Decimal | str = "1",
) -> ProbabilityForecast:
    return ProbabilityForecast(
        forecast_id=f"forecast_{juror_id}",
        case_id="case_probability",
        juror_id=juror_id,
        outcome=ForecastOutcome.ABOVE_STRIKE,
        probability=Decimal(probability),
        calibration_score=Decimal(calibration),
        confidence_stake=Decimal(stake),
        produced_at=NOW,
        horizon_at=NOW + timedelta(days=7),
        evidence_ids=("ev_probability",),
        rationale="Deterministic aggregation test.",
        invalidation="Evidence changes.",
        model_version="stub-v1",
        prompt_version="jury-v1",
    )


def test_consensus_jury_produces_deterministic_aggregate() -> None:
    result = aggregate_forecasts(
        (
            forecast("juror_market", "0.60"),
            forecast("juror_catalyst", "0.61"),
            forecast("juror_volatility", "0.59"),
        ),
        EXPECTED_JURORS,
    )

    assert result.status is AggregationStatus.READY
    assert result.probability == Decimal("0.60")
    assert result.disagreement == Decimal("0.02")
    assert [item.juror_id for item in result.contributions] == list(EXPECTED_JURORS)


def test_excessive_disagreement_forces_abstention() -> None:
    result = aggregate_forecasts(
        (
            forecast("juror_market", "0.70"),
            forecast("juror_catalyst", "0.30"),
            forecast("juror_volatility", "0.50"),
        ),
        EXPECTED_JURORS,
    )

    assert result.status is AggregationStatus.ABSTAIN
    assert result.reason == "juror_disagreement"
    assert result.disagreement == Decimal("0.40")


def test_low_calibration_shrinks_an_outlier_toward_half() -> None:
    result = aggregate_forecasts(
        (
            forecast("juror_market", "0.90", calibration="0.20"),
            forecast("juror_catalyst", "0.60", calibration="0.90"),
            forecast("juror_volatility", "0.60", calibration="0.90"),
        ),
        EXPECTED_JURORS,
    )

    assert result.status is AggregationStatus.READY
    assert result.contributions[0].calibrated_probability == Decimal("0.580")
    assert result.probability is not None
    assert Decimal("0.58") < result.probability < Decimal("0.60")


def test_missing_juror_forces_abstention() -> None:
    result = aggregate_forecasts(
        (
            forecast("juror_market", "0.60"),
            forecast("juror_catalyst", "0.60"),
        ),
        EXPECTED_JURORS,
    )

    assert result.status is AggregationStatus.ABSTAIN
    assert result.probability is None
    assert result.reason == "juror_set_incomplete"


def test_invalid_probability_is_rejected_before_aggregation() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        forecast("juror_market", "1.01")
