from decimal import Decimal

import pytest

from riskcourt.typesafe_calibration import (
    CalibrationObservation,
    abstention_rate,
    brier_score,
    disagreement_rate,
    log_loss,
    reliability_curve,
)


def test_calibration_metrics_ignore_abstentions_and_preserve_resolved_outcomes() -> None:
    observations = (
        CalibrationObservation(Decimal("0.8"), True, disagreed=True),
        CalibrationObservation(Decimal("0.2"), False),
        CalibrationObservation(Decimal("0.5"), True, abstained=True),
    )

    assert brier_score(observations) == Decimal("0.04")
    assert log_loss(observations) == Decimal("0.223144")
    assert abstention_rate(observations) == Decimal("0.333333")
    assert disagreement_rate(observations) == Decimal("0.333333")


def test_reliability_curve_has_bounded_buckets_and_observed_rates() -> None:
    curve = reliability_curve(
        (
            CalibrationObservation(Decimal("0.1"), False),
            CalibrationObservation(Decimal("0.9"), True),
        ),
        bins=2,
    )

    assert curve[0].count == 1
    assert curve[0].mean_probability == Decimal("0.1")
    assert curve[0].observed_rate == Decimal("0")
    assert curve[1].count == 1
    assert curve[1].observed_rate == Decimal("1")


def test_calibration_contract_rejects_out_of_range_probability() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        CalibrationObservation(Decimal("1.1"), True)

    with pytest.raises(ValueError, match="between 1 and 20"):
        reliability_curve((), bins=21)
