"""Code-owned calibration metrics for recorded TypeSafe shadow evaluations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import log

from riskcourt.strategy_math import calibrated_probability

EPSILON = Decimal("0.000001")
MIN_GROUP_SAMPLES = 20
MIN_TRAINING_SAMPLES = 10
MIN_HOLDOUT_SAMPLES = 5
HOLDOUT_FRACTION = Decimal("0.25")


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    """One resolved TypeSafe probability and its later binary outcome."""

    probability: Decimal
    realized: bool
    abstained: bool = False
    disagreed: bool = False

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.probability <= Decimal("1"):
            raise ValueError("calibration probability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ReliabilityBucket:
    lower_bound: Decimal
    upper_bound: Decimal
    count: int
    mean_probability: Decimal | None
    observed_rate: Decimal | None


@dataclass(frozen=True, slots=True)
class ForecastCalibrationSample:
    """One persisted forecast plus the time its event outcome became knowable."""

    decision_id: str
    forecast_id: str
    mode: str
    provider_mode: str
    juror_id: str
    model_version: str
    prompt_version: str
    calibration_version: str
    probability: Decimal
    calibration_score: Decimal
    realized: bool
    produced_at: datetime
    horizon_at: datetime
    resolved_at: datetime
    simulated: bool = False

    def __post_init__(self) -> None:
        if not all(
            (
                self.decision_id,
                self.forecast_id,
                self.mode,
                self.provider_mode,
                self.juror_id,
                self.model_version,
                self.prompt_version,
                self.calibration_version,
            )
        ):
            raise ValueError("calibration sample identifiers and versions are required")
        if self.mode not in {"recorded", "paper"}:
            raise ValueError("calibration sample mode is invalid")
        for value in (self.probability, self.calibration_score):
            if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
                raise ValueError("calibration sample probabilities must be between 0 and 1")
        timestamps = (self.produced_at, self.horizon_at, self.resolved_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValueError("calibration sample timestamps must be timezone-aware")
        if self.produced_at >= self.horizon_at or self.resolved_at < self.horizon_at:
            raise ValueError("calibration sample timing is inconsistent with its horizon")

    @property
    def prior_adjusted_probability(self) -> Decimal:
        return calibrated_probability(self.probability, self.calibration_score)


@dataclass(frozen=True, slots=True)
class CalibrationScores:
    brier_score: Decimal | None
    log_loss: Decimal | None


@dataclass(frozen=True, slots=True)
class ForecastCalibrationGroup:
    mode: str
    provider_mode: str
    juror_id: str
    model_version: str
    prompt_version: str
    calibration_version: str
    simulated: bool
    sample_count: int
    minimum_sample_count: int
    training_count: int
    holdout_count: int
    training_raw: CalibrationScores
    holdout_raw: CalibrationScores
    training_prior_adjusted: CalibrationScores
    holdout_prior_adjusted: CalibrationScores
    holdout_reliability: tuple[ReliabilityBucket, ...]
    status: str


def resolved_observations(
    observations: Iterable[CalibrationObservation],
) -> tuple[CalibrationObservation, ...]:
    return tuple(item for item in observations if not item.abstained)


def brier_score(observations: Iterable[CalibrationObservation]) -> Decimal | None:
    resolved = resolved_observations(observations)
    if not resolved:
        return None
    return _quantized(
        sum(
            ((item.probability - Decimal(int(item.realized))) ** 2 for item in resolved),
            start=Decimal("0"),
        )
        / Decimal(len(resolved))
    )


def log_loss(observations: Iterable[CalibrationObservation]) -> Decimal | None:
    resolved = resolved_observations(observations)
    if not resolved:
        return None
    total = Decimal("0")
    for item in resolved:
        probability = min(max(item.probability, EPSILON), Decimal("1") - EPSILON)
        total += (
            -Decimal(str(log(float(probability))))
            if item.realized
            else -Decimal(str(log(float(Decimal("1") - probability))))
        )
    return _quantized(total / Decimal(len(resolved)))


def reliability_curve(
    observations: Iterable[CalibrationObservation], *, bins: int = 5
) -> tuple[ReliabilityBucket, ...]:
    if bins < 1 or bins > 20:
        raise ValueError("reliability bins must be between 1 and 20")
    resolved = resolved_observations(observations)
    result: list[ReliabilityBucket] = []
    for index in range(bins):
        lower = Decimal(index) / Decimal(bins)
        upper = Decimal(index + 1) / Decimal(bins)
        bucket = tuple(
            item
            for item in resolved
            if lower <= item.probability < upper
            or (index == bins - 1 and item.probability == upper)
        )
        result.append(
            ReliabilityBucket(
                lower_bound=_quantized(lower),
                upper_bound=_quantized(upper),
                count=len(bucket),
                mean_probability=(
                    None
                    if not bucket
                    else _quantized(
                        sum((item.probability for item in bucket), start=Decimal("0"))
                        / Decimal(len(bucket))
                    )
                ),
                observed_rate=(
                    None
                    if not bucket
                    else _quantized(
                        sum((Decimal(int(item.realized)) for item in bucket), start=Decimal("0"))
                        / Decimal(len(bucket))
                    )
                ),
            )
        )
    return tuple(result)


def build_forecast_calibration_report(
    samples: Iterable[ForecastCalibrationSample], *, include_simulated: bool = False
) -> tuple[ForecastCalibrationGroup, ...]:
    """Score resolved forecasts with a chronological, outcome-available holdout.

    Training rows are eligible only when their outcomes were resolved before the
    first holdout forecast was produced. Low-sample groups expose counts only.
    Simulated rows are excluded by default and always remain a separate group.
    """

    groups: dict[
        tuple[str, str, str, str, str, str, bool], list[ForecastCalibrationSample]
    ] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for sample in samples:
        if sample.simulated and not include_simulated:
            continue
        identity = (sample.decision_id, sample.forecast_id)
        if identity in seen:
            raise ValueError("calibration report contains a duplicate forecast")
        seen.add(identity)
        groups[
            (
                sample.mode,
                sample.provider_mode,
                sample.juror_id,
                sample.model_version,
                sample.prompt_version,
                sample.calibration_version,
                sample.simulated,
            )
        ].append(sample)

    result: list[ForecastCalibrationGroup] = []
    for key in sorted(groups):
        items = sorted(
            groups[key],
            key=lambda item: (
                item.produced_at.astimezone(UTC),
                item.decision_id,
                item.forecast_id,
            ),
        )
        empty = CalibrationScores(None, None)
        if len(items) < MIN_GROUP_SAMPLES:
            result.append(
                ForecastCalibrationGroup(
                    *key,
                    sample_count=len(items),
                    minimum_sample_count=MIN_GROUP_SAMPLES,
                    training_count=0,
                    holdout_count=0,
                    training_raw=empty,
                    holdout_raw=empty,
                    training_prior_adjusted=empty,
                    holdout_prior_adjusted=empty,
                    holdout_reliability=(),
                    status="insufficient_sample",
                )
            )
            continue

        split_index = max(1, int(len(items) * (Decimal("1") - HOLDOUT_FRACTION)))
        cutoff = items[split_index].produced_at.astimezone(UTC)
        while split_index > 0 and items[split_index - 1].produced_at.astimezone(UTC) == cutoff:
            split_index -= 1
        holdout = items[split_index:]
        training_candidates = items[:split_index]
        training = [
            item for item in training_candidates if item.resolved_at.astimezone(UTC) < cutoff
        ]
        if len(training) < MIN_TRAINING_SAMPLES or len(holdout) < MIN_HOLDOUT_SAMPLES:
            status = "insufficient_chronological_history"
            train_raw = holdout_raw = train_prior = holdout_prior = empty
            holdout_curve: tuple[ReliabilityBucket, ...] = ()
        else:
            status = "evaluated"
            train_raw = _score_samples(training, prior_adjusted=False)
            holdout_raw = _score_samples(holdout, prior_adjusted=False)
            train_prior = _score_samples(training, prior_adjusted=True)
            holdout_prior = _score_samples(holdout, prior_adjusted=True)
            holdout_curve = reliability_curve(
                tuple(
                    CalibrationObservation(item.probability, item.realized)
                    for item in holdout
                )
            )
        result.append(
            ForecastCalibrationGroup(
                *key,
                sample_count=len(items),
                minimum_sample_count=MIN_GROUP_SAMPLES,
                training_count=len(training),
                holdout_count=len(holdout),
                training_raw=train_raw,
                holdout_raw=holdout_raw,
                training_prior_adjusted=train_prior,
                holdout_prior_adjusted=holdout_prior,
                holdout_reliability=holdout_curve,
                status=status,
            )
        )
    return tuple(result)


def _score_samples(
    samples: Iterable[ForecastCalibrationSample], *, prior_adjusted: bool
) -> CalibrationScores:
    observations = tuple(
        CalibrationObservation(
            item.prior_adjusted_probability if prior_adjusted else item.probability,
            item.realized,
        )
        for item in samples
    )
    return CalibrationScores(brier_score(observations), log_loss(observations))


def abstention_rate(observations: Iterable[CalibrationObservation]) -> Decimal:
    items = tuple(observations)
    if not items:
        return Decimal("0")
    return _quantized(
        Decimal(sum(item.abstained for item in items)) / Decimal(len(items))
    )


def disagreement_rate(observations: Iterable[CalibrationObservation]) -> Decimal:
    items = tuple(observations)
    if not items:
        return Decimal("0")
    return _quantized(
        Decimal(sum(item.disagreed for item in items)) / Decimal(len(items))
    )


def _quantized(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001")).normalize()
