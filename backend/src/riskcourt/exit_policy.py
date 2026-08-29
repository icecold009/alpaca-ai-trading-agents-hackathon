"""Deterministic position lifecycle policy; no model input can widen risk."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum


class PositionAction(StrEnum):
    ENTER = "enter"
    HOLD = "hold"
    EXIT = "exit"
    BLOCK_ENTRY = "block_entry"


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    profit_target_multiple: Decimal = Decimal("1.5")
    protective_value_multiple: Decimal = Decimal("0.5")
    maximum_quote_age: timedelta = timedelta(seconds=30)
    exit_days_before_expiry: int = 2


DEFAULT_EXIT_POLICY = ExitPolicy()


@dataclass(frozen=True, slots=True)
class PositionState:
    has_position: bool
    entry_debit: Decimal
    current_value: Decimal
    probability_edge: Decimal
    quote_age: timedelta
    days_to_expiry: int
    kill_switch_enabled: bool


@dataclass(frozen=True, slots=True)
class PositionDecision:
    action: PositionAction
    reason: str


def evaluate_position(
    state: PositionState,
    policy: ExitPolicy = DEFAULT_EXIT_POLICY,
) -> PositionDecision:
    if state.entry_debit <= 0 or state.current_value < 0:
        raise ValueError("entry debit must be positive and current value cannot be negative")
    if state.quote_age < timedelta(0):
        raise ValueError("quote age cannot be negative")

    if state.kill_switch_enabled:
        return PositionDecision(
            PositionAction.EXIT if state.has_position else PositionAction.BLOCK_ENTRY,
            "kill_switch_enabled",
        )
    if state.quote_age > policy.maximum_quote_age:
        return PositionDecision(
            PositionAction.EXIT if state.has_position else PositionAction.BLOCK_ENTRY,
            "quote_stale",
        )
    if not state.has_position:
        return PositionDecision(PositionAction.ENTER, "entry_checks_passed")
    if state.days_to_expiry <= policy.exit_days_before_expiry:
        return PositionDecision(PositionAction.EXIT, "expiry_risk")
    if state.current_value >= state.entry_debit * policy.profit_target_multiple:
        return PositionDecision(PositionAction.EXIT, "profit_target")
    if state.current_value <= state.entry_debit * policy.protective_value_multiple:
        return PositionDecision(PositionAction.EXIT, "protective_loss_exit")
    if state.probability_edge <= 0:
        return PositionDecision(PositionAction.EXIT, "edge_decayed")
    return PositionDecision(PositionAction.HOLD, "position_within_exit_envelope")
