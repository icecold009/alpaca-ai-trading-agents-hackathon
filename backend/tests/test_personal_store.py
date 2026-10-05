import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.personal_store import PersonalStore


def recorded_payload() -> dict[str, object]:
    case = RecordedCaseRepository().get("case_edge_positive")
    assert case is not None
    return case.model_dump(mode="json")


def paper_approval(
    store: PersonalStore, quantity: int = 1
) -> tuple[str, str, dict[str, Any]]:
    payload = recorded_payload()
    payload["as_of"] = datetime.now(UTC).isoformat()
    payload["underlying_symbol"] = "SPY"
    payload["forecasts"] = []
    payload["verdict"] = {
        "decision": "approve",
        "approved_quantity": quantity,
        "maximum_loss": str(100 * quantity),
    }
    payload["account"] = {
        "account": {"equity": "100000", "last_equity": "100000"}
    }
    scan_id = store.create_scan("paper", ["SPY"])
    decision_id = store.save_decision(scan_id=scan_id, mode="paper", payload=payload)
    approval = store.create_approval(
        decision_id,
        approval_id="approval_store_test",
        client_order_id="rc_store_test",
        request_sha256="a" * 64,
        account_equity="100000",
        account_last_equity="100000",
    )
    return scan_id, decision_id, approval


def test_personal_store_seeds_bounded_watchlist_and_persists_decisions(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    assert [item["symbol"] for item in store.watchlist()] == ["SPY", "QQQ"]

    scan_id, decision_id, approval = paper_approval(store)
    store.finish_scan(scan_id)

    decision = store.get_decision(decision_id)
    assert decision is not None
    assert decision["symbol"] == "SPY"
    assert decision["payload"]["case_id"] == "case_edge_positive"

    assert approval["status"] == "prepared"
    submission = store.reserve_approval_submission(
        approval["approval_id"], "rc_store_test", "a" * 64
    )
    assert submission["replayed"] is False
    replay = store.reserve_approval_submission(
        approval["approval_id"], "rc_store_test", "a" * 64
    )
    assert replay["replayed"] is True
    assert replay["order"]["client_order_id"] == submission["order"]["client_order_id"]
    with pytest.raises(ValueError, match="different order request"):
        store.reserve_approval_submission(
            approval["approval_id"], "rc_store_test", "b" * 64
        )

    position = store.create_position(
        decision_id=decision_id,
        order_id=submission["order"]["order_id"],
        symbol="SPY",
        direction="bullish",
        cost_basis="150",
    )
    assert position["status"] == "open"
    exit_approval = store.create_exit_approval(
        position["position_id"],
        approval_id="approval_exit_test",
        client_order_id="rc_store_exit",
        request_sha256="b" * 64,
    )
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


def test_risk_exposure_counts_submitting_entry_and_persistent_kill_switch(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    _, decision_id, approval = paper_approval(store)
    store.reserve_approval_submission(
        approval["approval_id"], "rc_store_test", "a" * 64
    )

    exposure = store.risk_exposure(mode="paper")
    assert exposure.open_options_risk == Decimal("100")
    assert exposure.open_option_positions == 0
    assert exposure.pending_option_orders == 1
    assert exposure.kill_switch_enabled is False

    store.set_kill_switch(True, "operator pause")
    assert store.risk_exposure(mode="paper").kill_switch_enabled is True
    assert store.get_decision(decision_id) is not None


def test_daily_equity_baseline_survives_restart_and_rolls_by_trading_day(tmp_path: Path) -> None:
    path = tmp_path / "riskcourt.sqlite3"
    store = PersonalStore(path)
    baseline = store.daily_equity_baseline(
        trading_day="2026-10-04", broker_last_equity=Decimal("100000")
    )
    store.close()

    recovered = PersonalStore(path)
    assert recovered.daily_equity_baseline(
        trading_day="2026-10-04", broker_last_equity=None
    ) == Decimal("100000")
    assert recovered.daily_equity_baseline(
        trading_day="2026-10-05", broker_last_equity=None
    ) is None
    assert baseline == Decimal("100000")
    recovered.close()


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


def test_schema_v1_migrates_submission_fingerprint_column(tmp_path: Path) -> None:
    path = tmp_path / "riskcourt.sqlite3"
    store = PersonalStore(path)
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE orders DROP COLUMN request_sha256")
        connection.execute("PRAGMA user_version = 1")

    migrated = PersonalStore(path)

    assert migrated._connection.execute("PRAGMA user_version").fetchone()[0] == 10
    columns = {
        row[1] for row in migrated._connection.execute("PRAGMA table_info(orders)").fetchall()
    }
    assert "request_sha256" in columns
    approval_columns = {
        row[1]
        for row in migrated._connection.execute("PRAGMA table_info(approvals)").fetchall()
    }
    assert {
        "client_order_id",
        "request_sha256",
        "account_equity",
        "account_last_equity",
        "decision_sha256",
    } <= approval_columns
    position_columns = {
        row[1]
        for row in migrated._connection.execute("PRAGMA table_info(positions)").fetchall()
    }
    order_columns = {
        row[1] for row in migrated._connection.execute("PRAGMA table_info(orders)").fetchall()
    }
    assert {
        "quantity",
        "mark_at",
        "reconciliation_status",
        "reconciliation_reason",
    } <= position_columns
    assert {"filled_qty", "accounted_filled_qty", "filled_avg_price", "updated_at"} <= (
        order_columns
    )
    migrated.close()


def test_veto_revokes_prepared_approval_and_prevents_reapproval(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    scan_id = store.create_scan("recorded", ["SPY"])
    decision_id = store.save_decision(
        scan_id=scan_id,
        mode="recorded",
        payload=recorded_payload(),
    )
    approval = store.create_approval(decision_id)

    decision = store.veto_decision(decision_id)

    assert decision["status"] == "vetoed"
    revoked = store.get_approval(approval["approval_id"])
    assert revoked is not None
    assert revoked["status"] == "revoked"
    with pytest.raises(ValueError, match="vetoed"):
        store.create_approval(decision_id)
    with pytest.raises(ValueError, match="revoked"):
        store.reserve_approval_submission(
            approval["approval_id"], "riskcourt_vetoed_order", "b" * 64
        )


def test_duplicate_approvals_share_one_active_entry_approval(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    scan_id = store.create_scan("recorded", ["SPY"])
    decision_id = store.save_decision(
        scan_id=scan_id,
        mode="recorded",
        payload=recorded_payload(),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        approvals = list(executor.map(lambda _: store.create_approval(decision_id), range(8)))

    assert len({approval["approval_id"] for approval in approvals}) == 1
    active = [
        approval
        for approval in store._connection.execute(
            "SELECT * FROM approvals WHERE decision_id = ? "
            "AND kind = 'entry' AND status = 'prepared'",
            (decision_id,),
        ).fetchall()
    ]
    assert len(active) == 1


def test_submitted_decision_cannot_be_vetoed(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    _, decision_id, approval = paper_approval(store)
    store.reserve_approval_submission(
        approval["approval_id"], "rc_store_test", "a" * 64
    )

    with pytest.raises(ValueError, match="submitted"):
        store.veto_decision(decision_id)


def test_kill_switch_blocks_atomic_entry_reservation(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    _, _, approval = paper_approval(store)
    store.set_kill_switch(True, "operator pause")

    with pytest.raises(ValueError, match="kill switch"):
        store.reserve_approval_submission(
            approval["approval_id"], "rc_store_test", "a" * 64
        )
    assert store.orders() == []
    unchanged = store.get_approval(approval["approval_id"])
    assert unchanged is not None
    assert unchanged["status"] == "prepared"


def test_reconciliation_accounts_for_later_and_partial_entry_and_exit_fills(
    tmp_path: Path,
) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    _, decision_id, approval = paper_approval(store, quantity=2)
    reservation = store.reserve_approval_submission(
        approval["approval_id"], "rc_store_test", "a" * 64
    )
    order_id = reservation["order"]["order_id"]

    partial = store.reconcile_order_update(
        order_id,
        status="partially_filled",
        filled_qty="1",
        filled_avg_price="0.30",
        filled_at=datetime.now(UTC).isoformat(),
    )
    position = store.positions()[0]
    assert partial["accounted_filled_qty"] == "1"
    assert position["quantity"] == "1"
    assert position["cost_basis"] == "30.00"

    filled = store.reconcile_order_update(
        order_id,
        status="filled",
        filled_qty="2",
        filled_avg_price="0.28",
        filled_at=datetime.now(UTC).isoformat(),
    )
    position = store.positions()[0]
    assert filled["accounted_filled_qty"] == "2"
    assert position["quantity"] == "2"
    assert position["cost_basis"] == "56.00"

    exit_approval = store.create_exit_approval(
        position["position_id"],
        approval_id="approval_exit_test",
        client_order_id="rc_store_exit",
        request_sha256="b" * 64,
    )
    assert exit_approval["quantity"] == 2
    exit_reservation = store.reserve_approval_submission(
        exit_approval["approval_id"], "rc_store_exit", "b" * 64
    )
    closed = store.reconcile_order_update(
        exit_reservation["order"]["order_id"],
        status="partially_filled",
        filled_qty="1",
        filled_avg_price="-0.40",
        filled_at=datetime.now(UTC).isoformat(),
    )
    assert closed["status"] == "partially_filled"
    position = store.positions()[0]
    assert position["quantity"] == "1"
    assert position["realized_pnl"] == "12.00"

    store.reconcile_order_update(
        exit_reservation["order"]["order_id"],
        status="filled",
        filled_qty="2",
        filled_avg_price="-0.375",
        filled_at=datetime.now(UTC).isoformat(),
    )
    position = store.positions()[0]
    assert position["status"] == "closed"
    assert position["quantity"] == "0"
    assert position["realized_pnl"] == "21.500"
    assert store.get_decision(decision_id) is not None
