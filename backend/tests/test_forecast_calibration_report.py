from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from riskcourt.typesafe_calibration import (
    ForecastCalibrationSample,
    build_forecast_calibration_report,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def samples(
    count: int,
    *,
    simulated: bool = False,
    mode: str = "paper",
    resolved_after_cutoff: bool = False,
) -> list[ForecastCalibrationSample]:
    rows = []
    cutoff = START + timedelta(days=int(count * Decimal("0.75")))
    for index in range(count):
        produced_at = START + timedelta(days=index)
        horizon_at = produced_at + timedelta(minutes=1)
        resolved_at = (
            cutoff + timedelta(seconds=30)
            if resolved_after_cutoff and index < int(count * Decimal("0.75"))
            else horizon_at + timedelta(minutes=1)
        )
        rows.append(
            ForecastCalibrationSample(
                decision_id=f"decision_{mode}_{simulated}_{index}",
                forecast_id="forecast_market",
                mode=mode,
                provider_mode="typesafe",
                juror_id="juror_market",
                model_version="model-v1",
                prompt_version="prompt-v2",
                calibration_version="configured_shrinkage_prior_v1",
                probability=Decimal("0.7") if index % 2 == 0 else Decimal("0.3"),
                calibration_score=Decimal("0.8"),
                realized=index % 2 == 0,
                produced_at=produced_at,
                horizon_at=horizon_at,
                resolved_at=resolved_at,
                simulated=simulated,
            )
        )
    return rows


def test_report_uses_chronological_holdout_and_code_owned_prior() -> None:
    result = build_forecast_calibration_report(samples(20))

    assert len(result) == 1
    group = result[0]
    assert group.status == "evaluated"
    assert group.sample_count == 20
    assert group.training_count == 15
    assert group.holdout_count == 5
    assert group.training_raw.brier_score == Decimal("0.09")
    assert group.holdout_raw.brier_score == Decimal("0.09")
    assert group.holdout_prior_adjusted.brier_score is not None
    assert len(group.holdout_reliability) == 5


def test_report_withholds_scores_when_minimum_sample_is_not_met() -> None:
    group = build_forecast_calibration_report(samples(19))[0]
    assert group.status == "insufficient_sample"
    assert group.sample_count == 19
    assert group.training_raw.brier_score is None
    assert group.holdout_raw.log_loss is None


def test_training_excludes_outcomes_not_known_before_holdout_started() -> None:
    group = build_forecast_calibration_report(
        samples(20, resolved_after_cutoff=True)
    )[0]
    assert group.status == "insufficient_chronological_history"
    assert group.training_count == 0
    assert group.holdout_count == 5
    assert group.training_raw.brier_score is None


def test_simulated_and_runtime_modes_remain_separate_groups() -> None:
    rows = samples(20) + samples(20, simulated=True) + samples(20, mode="recorded")

    default_groups = build_forecast_calibration_report(rows)
    assert len(default_groups) == 2
    assert {group.mode for group in default_groups} == {"paper", "recorded"}
    assert {group.simulated for group in default_groups} == {False}

    with_simulated = build_forecast_calibration_report(rows, include_simulated=True)
    assert len(with_simulated) == 3
    assert sum(group.simulated for group in with_simulated) == 1


def test_report_rejects_duplicate_forecast_rows_and_early_resolution() -> None:
    sample = samples(20)[0]
    with pytest.raises(ValueError, match="duplicate forecast"):
        build_forecast_calibration_report([sample, sample])
    with pytest.raises(ValueError, match="timing is inconsistent"):
        replace(sample, resolved_at=sample.horizon_at - timedelta(seconds=1))
