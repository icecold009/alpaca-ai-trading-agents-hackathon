"""Code-owned calibration metrics for recorded TypeSafe shadow evaluations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from math import log

EPSILON = Decimal("0.000001")


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
