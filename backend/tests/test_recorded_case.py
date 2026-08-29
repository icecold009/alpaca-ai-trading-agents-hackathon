import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from riskcourt.domain import DecisionEventType, ExecutionStatus, VerdictDecision
from riskcourt.recorded_case import RecordedCase

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "cases" / "edge-positive.json"
VETO_FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "cases" / "insufficient-edge.json"


def load_fixture_payload() -> dict[str, object]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_edge_positive_fixture_is_fully_linked_and_reconstructable() -> None:
    case = RecordedCase.model_validate(load_fixture_payload())

    assert case.recorded is True
    assert case.strategy.probability_edge > case.strategy.minimum_edge
    assert case.verdict.decision is VerdictDecision.RESIZE
    assert case.verdict.approved_quantity == 1
    assert case.approval is not None
    assert case.approval.maximum_loss == Decimal("150")
    assert case.executions[-1].status is ExecutionStatus.FILLED
    assert case.pnl_snapshots[-1].unrealized_pnl == Decimal("25")


def test_edge_positive_fixture_round_trips_through_json() -> None:
    case = RecordedCase.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert RecordedCase.model_validate_json(case.model_dump_json()) == case


def test_tampered_maximum_loss_is_rejected() -> None:
    payload = load_fixture_payload()
    approval = payload["approval"]
    assert isinstance(approval, dict)
    approval["maximum_loss"] = "149.99"

    with pytest.raises(ValidationError, match="maximum loss must be reconstructable"):
        RecordedCase.model_validate(payload)


def test_insufficient_edge_fixture_vetoes_without_execution() -> None:
    case = RecordedCase.model_validate_json(VETO_FIXTURE_PATH.read_text(encoding="utf-8"))

    assert case.strategy.probability_edge < case.strategy.minimum_edge
    assert case.verdict.decision is VerdictDecision.VETO
    assert case.approval is None
    assert case.executions == ()
    assert case.pnl_snapshots == ()
    assert all(event.event_type is not DecisionEventType.EXECUTION_UPDATED for event in case.events)
