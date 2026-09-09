from pathlib import Path

import pytest

from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.personal_store import PersonalStore


def recorded_payload() -> dict[str, object]:
    case = RecordedCaseRepository().get("case_edge_positive")
    assert case is not None
    return case.model_dump(mode="json")


def test_personal_store_seeds_bounded_watchlist_and_persists_decisions(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    assert [item["symbol"] for item in store.watchlist()] == ["SPY", "QQQ"]

    scan_id = store.create_scan("recorded", ["SPY"])
    decision_id = store.save_decision(
        scan_id=scan_id,
        mode="recorded",
        payload=recorded_payload(),
    )
    store.finish_scan(scan_id)

    decision = store.get_decision(decision_id)
    assert decision is not None
    assert decision["symbol"] == "SPY"
    assert decision["payload"]["case_id"] == "case_edge_positive"

    approval = store.create_approval(decision_id)
    assert approval["status"] == "prepared"
    submission = store.submit_approval(approval["approval_id"], "riskcourt_test_order_1")
    assert submission["replayed"] is False
    replay = store.submit_approval(approval["approval_id"], "riskcourt_test_order_1")
    assert replay["replayed"] is True

    position = store.create_position(
        decision_id=decision_id,
        order_id=submission["order"]["order_id"],
        symbol="SPY",
        direction="bullish",
        cost_basis="150",
    )
    assert position["status"] == "open"
    exit_approval = store.create_exit_approval(position["position_id"])
    assert exit_approval["kind"] == "exit"
    assert exit_approval["position_id"] == position["position_id"]
    prepared_exit = store.prepared_exit_approval(position["position_id"])
    assert prepared_exit is not None
    assert prepared_exit["approval_id"] == exit_approval["approval_id"]
    closed = store.update_position(
        position["position_id"],
        status="closed",
        position_value="0",
        unrealized_pnl="0",
        realized_pnl="25",
    )
    assert closed["realized_pnl"] == "25"


def test_personal_store_rejects_unsupported_symbols_and_validates_journal(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    with pytest.raises(ValueError, match="only SPY and QQQ"):
        store.replace_watchlist(["AAPL"])
    with pytest.raises(ValueError, match="journal body"):
        store.add_journal_entry(" ")

    state = store.set_kill_switch(True, "operator pause")
    assert state["enabled"] is True
    assert state["reason"] == "operator pause"


def test_personal_store_audit_export_and_restart_recovery(tmp_path: Path) -> None:
    path = tmp_path / "riskcourt.sqlite3"
    store = PersonalStore(path)
    store.record_audit("test.event", "safe-order", {"order_id": "broker-secret"})
    exported = store.export_json()
    assert "broker-secret" not in exported
    assert "[REDACTED]" in exported
    assert store.audit_history()[0]["event_type"] == "test.event"
    store.close()

    recovered = PersonalStore(path)
    assert [item["symbol"] for item in recovered.watchlist()] == ["SPY", "QQQ"]
    recovered.close()
