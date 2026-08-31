import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from riskcourt.domain import DecisionEvent, DecisionEventType
from riskcourt.event_store import AppendOnlyDecisionLog

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)


def event(
    sequence: int, event_type: DecisionEventType, payload: dict[str, object]
) -> DecisionEvent:
    return DecisionEvent.model_validate(
        {
            "event_id": f"event_{sequence:02d}",
            "case_id": "case_event_log",
            "sequence": sequence,
            "event_type": event_type,
            "occurred_at": NOW + timedelta(seconds=sequence),
            "evidence_ids": ("ev_event_log",),
            "payload": payload,
        }
    )


def populated_log() -> AppendOnlyDecisionLog:
    log = AppendOnlyDecisionLog("case_event_log")
    log.append(
        event(
            0,
            DecisionEventType.CASE_OPENED,
            {"recorded": True, "alpaca_account_id": "paper-account-sensitive"},
        )
    )
    log.append(
        event(
            1,
            DecisionEventType.APPROVAL_ISSUED,
            {"approval_id": "approval_event_log"},
        )
    )
    log.append(
        event(
            2,
            DecisionEventType.EXECUTION_UPDATED,
            {"status": "filled", "client_order_id": "paper-order-sensitive"},
        )
    )
    log.append(
        event(
            3,
            DecisionEventType.PNL_RECORDED,
            {"unrealized_pnl": "25"},
        )
    )
    return log


def test_persist_export_and_replay_round_trip(tmp_path: Path) -> None:
    original = populated_log()
    log_path = tmp_path / "decision-log.json"
    log_path.write_text(original.to_json(), encoding="utf-8")

    replayed = AppendOnlyDecisionLog.from_json(
        "case_event_log",
        log_path.read_text(encoding="utf-8"),
    )
    projection = replayed.project()
    card = replayed.export_decision_card()
    card_json = card.model_dump_json()

    assert replayed.events == original.events
    assert projection.execution_status == "filled"
    assert projection.unrealized_pnl == 25
    assert card.head_hash == replayed.events[-1].event_hash
    assert "paper-account-sensitive" not in card_json
    assert "paper-order-sensitive" not in card_json
    assert "[REDACTED]" in card_json


@pytest.mark.parametrize("mutation", ["change", "delete", "reorder"])
def test_tampering_is_detected(mutation: str) -> None:
    payload = json.loads(populated_log().to_json())
    assert isinstance(payload, list)
    if mutation == "change":
        payload[1]["event"]["payload"]["approval_id"] = "changed"
    elif mutation == "delete":
        payload.pop(1)
    else:
        payload[1], payload[2] = payload[2], payload[1]

    with pytest.raises(ValueError, match="changed|reordered"):
        AppendOnlyDecisionLog.from_json("case_event_log", json.dumps(payload))
