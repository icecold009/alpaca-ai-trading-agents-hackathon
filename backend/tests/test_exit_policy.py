from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from riskcourt.exit_policy import PositionAction, PositionState, evaluate_position


def safe_position() -> PositionState:
    return PositionState(
        has_position=True,
        entry_debit=Decimal("1.50"),
        current_value=Decimal("1.60"),
        probability_edge=Decimal("0.10"),
        quote_age=timedelta(seconds=5),
        days_to_expiry=10,
        kill_switch_enabled=False,
    )


@pytest.mark.parametrize(
    ("state", "action", "reason"),
    [
        (replace(safe_position(), has_position=False), PositionAction.ENTER, "entry_checks_passed"),
        (safe_position(), PositionAction.HOLD, "position_within_exit_envelope"),
        (
            replace(safe_position(), current_value=Decimal("2.25")),
            PositionAction.EXIT,
            "profit_target",
        ),
        (
            replace(safe_position(), current_value=Decimal("0.75")),
            PositionAction.EXIT,
            "protective_loss_exit",
        ),
        (
            replace(safe_position(), quote_age=timedelta(seconds=31)),
            PositionAction.EXIT,
            "quote_stale",
        ),
        (
            replace(safe_position(), days_to_expiry=2),
            PositionAction.EXIT,
            "expiry_risk",
        ),
        (
            replace(safe_position(), kill_switch_enabled=True),
            PositionAction.EXIT,
            "kill_switch_enabled",
        ),
    ],
)
def test_deterministic_position_lifecycle(
    state: PositionState,
    action: PositionAction,
    reason: str,
) -> None:
    result = evaluate_position(state)

    assert result.action is action
    assert result.reason == reason


def test_edge_decay_exits_without_model_discretion() -> None:
    result = evaluate_position(replace(safe_position(), probability_edge=Decimal("0")))

    assert result.action is PositionAction.EXIT
    assert result.reason == "edge_decayed"
