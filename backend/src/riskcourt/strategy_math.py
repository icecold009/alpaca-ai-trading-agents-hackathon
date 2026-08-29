"""Deterministic probability-edge and defined-risk sizing formulas."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

ZERO = Decimal("0")
ONE = Decimal("1")
HALF = Decimal("0.5")
OPTION_MULTIPLIER = Decimal("100")


@dataclass(frozen=True, slots=True)
class JurorEstimate:
    probability: Decimal
    calibration_score: Decimal
    confidence_stake: Decimal


@dataclass(frozen=True, slots=True)
class EdgeCalculation:
    jury_probability: Decimal
    market_hurdle: Decimal
    probability_edge: Decimal
    minimum_edge: Decimal

    @property
    def clears_threshold(self) -> bool:
        return self.probability_edge >= self.minimum_edge


def _require_unit_interval(name: str, value: Decimal) -> None:
    if not ZERO <= value <= ONE:
        raise ValueError(f"{name} must be between 0 and 1")


def calibrated_probability(probability: Decimal, calibration_score: Decimal) -> Decimal:
    """Shrink a forecast toward 0.5 according to its declared calibration score."""

    _require_unit_interval("probability", probability)
    _require_unit_interval("calibration_score", calibration_score)
    return HALF + calibration_score * (probability - HALF)


def aggregate_juror_probability(estimates: tuple[JurorEstimate, ...]) -> Decimal:
    """Return the calibration-and-confidence-weighted jury probability."""

    if not estimates:
        raise ValueError("at least one juror estimate is required")

    weighted_sum = ZERO
    total_weight = ZERO
    for estimate in estimates:
        _require_unit_interval("confidence_stake", estimate.confidence_stake)
        calibrated = calibrated_probability(
            estimate.probability,
            estimate.calibration_score,
        )
        weight = estimate.calibration_score * estimate.confidence_stake
        weighted_sum += calibrated * weight
        total_weight += weight

    if total_weight == ZERO:
        raise ValueError("juror estimates must have positive total weight")
    return weighted_sum / total_weight


def option_implied_hurdle(
    net_debit: Decimal,
    spread_width: Decimal,
    slippage_buffer: Decimal = ZERO,
) -> Decimal:
    """Calculate the debit/width payoff-geometry proxy, including slippage."""

    if spread_width <= ZERO:
        raise ValueError("spread_width must be positive")
    if net_debit <= ZERO:
        raise ValueError("net_debit must be positive")
    if slippage_buffer < ZERO:
        raise ValueError("slippage_buffer cannot be negative")
    hurdle = (net_debit + slippage_buffer) / spread_width
    if hurdle > ONE:
        raise ValueError("debit plus slippage cannot exceed spread width")
    return hurdle


def calculate_edge(
    estimates: tuple[JurorEstimate, ...],
    net_debit: Decimal,
    spread_width: Decimal,
    slippage_buffer: Decimal,
    minimum_edge: Decimal,
) -> EdgeCalculation:
    _require_unit_interval("minimum_edge", minimum_edge)
    jury_probability = aggregate_juror_probability(estimates)
    market_hurdle = option_implied_hurdle(net_debit, spread_width, slippage_buffer)
    return EdgeCalculation(
        jury_probability=jury_probability,
        market_hurdle=market_hurdle,
        probability_edge=jury_probability - market_hurdle,
        minimum_edge=minimum_edge,
    )


def maximum_loss_per_contract(net_debit: Decimal, estimated_fees: Decimal = ZERO) -> Decimal:
    if net_debit <= ZERO:
        raise ValueError("net_debit must be positive")
    if estimated_fees < ZERO:
        raise ValueError("estimated_fees cannot be negative")
    return net_debit * OPTION_MULTIPLIER + estimated_fees


def defined_risk_contracts(
    account_equity: Decimal,
    maximum_loss: Decimal,
    risk_fraction: Decimal = Decimal("0.005"),
    contract_cap: int = 1,
) -> int:
    """Size from fixed capital limits; model output is deliberately absent."""

    if account_equity <= ZERO or maximum_loss <= ZERO:
        raise ValueError("account_equity and maximum_loss must be positive")
    if not ZERO < risk_fraction <= ONE:
        raise ValueError("risk_fraction must be greater than 0 and at most 1")
    if contract_cap < 1:
        raise ValueError("contract_cap must be at least 1")

    affordable = (account_equity * risk_fraction / maximum_loss).to_integral_value(
        rounding=ROUND_FLOOR
    )
    return min(contract_cap, int(affordable))
