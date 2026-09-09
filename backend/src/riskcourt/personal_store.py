"""Local-first persistence for the RiskCourt personal workstation.

The store deliberately uses the standard-library SQLite driver.  The database
is local application state, while the domain and audit contracts remain owned
by the existing Pydantic models and hash-chained event log.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_WATCHLIST = ("SPY", "QQQ")
ALLOWED_SYMBOLS = frozenset(DEFAULT_WATCHLIST)
SCHEMA_VERSION = 1


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


class PersonalStore:
    """Thread-safe, parameterized SQLite repository for local product state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def migrate(self) -> None:
        """Apply the immutable local schema migration exactly once."""

        with self._lock:
            current = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            if current > SCHEMA_VERSION:
                raise RuntimeError("personal database schema is newer than this application")
            if current == 0:
                self._connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS watchlist (
                        symbol TEXT PRIMARY KEY,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        sort_order INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS scan_runs (
                        scan_id TEXT PRIMARY KEY,
                        mode TEXT NOT NULL,
                        status TEXT NOT NULL,
                        symbols_json TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        error TEXT
                    );
                    CREATE TABLE IF NOT EXISTS decisions (
                        decision_id TEXT PRIMARY KEY,
                        scan_id TEXT NOT NULL,
                        case_id TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        verdict TEXT NOT NULL,
                        status TEXT NOT NULL,
                        as_of TEXT NOT NULL,
                        freshness_until TEXT NOT NULL,
                        maximum_loss TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        FOREIGN KEY(scan_id) REFERENCES scan_runs(scan_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_decisions_created
                        ON decisions(created_at DESC);
                    CREATE TABLE IF NOT EXISTS approvals (
                        approval_id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL,
                        kind TEXT NOT NULL DEFAULT 'entry',
                        position_id TEXT,
                        status TEXT NOT NULL,
                        approved_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        maximum_loss TEXT NOT NULL,
                        idempotency_key TEXT UNIQUE,
                        submitted_at TEXT,
                        FOREIGN KEY(decision_id) REFERENCES decisions(decision_id)
                    );
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL,
                        approval_id TEXT NOT NULL,
                        client_order_id TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        submitted_at TEXT NOT NULL,
                        filled_at TEXT,
                        filled_debit TEXT,
                        safe_reference TEXT,
                        FOREIGN KEY(decision_id) REFERENCES decisions(decision_id),
                        FOREIGN KEY(approval_id) REFERENCES approvals(approval_id)
                    );
                    CREATE TABLE IF NOT EXISTS positions (
                        position_id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL,
                        order_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        status TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        cost_basis TEXT NOT NULL,
                        position_value TEXT NOT NULL,
                        unrealized_pnl TEXT NOT NULL,
                        realized_pnl TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(decision_id) REFERENCES decisions(decision_id),
                        FOREIGN KEY(order_id) REFERENCES orders(order_id)
                    );
                    CREATE TABLE IF NOT EXISTS journal_entries (
                        entry_id TEXT PRIMARY KEY,
                        decision_id TEXT,
                        body TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(decision_id) REFERENCES decisions(decision_id)
                    );
                    CREATE TABLE IF NOT EXISTS kill_switch (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        enabled INTEGER NOT NULL DEFAULT 0,
                        reason TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS audit_events (
                        audit_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        previous_hash TEXT,
                        event_hash TEXT NOT NULL UNIQUE
                    );
                    INSERT OR IGNORE INTO kill_switch(singleton, enabled, reason, updated_at)
                        VALUES(1, 0, '', CURRENT_TIMESTAMP);
                    PRAGMA user_version = 1;
                    """
                )
                self._seed_watchlist()
            self._ensure_approval_columns()
            self._ensure_audit_table()

    def _ensure_approval_columns(self) -> None:
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(approvals)").fetchall()
        }
        if "kind" not in columns:
            self._connection.execute(
                "ALTER TABLE approvals ADD COLUMN kind TEXT NOT NULL DEFAULT 'entry'"
            )
        if "position_id" not in columns:
            self._connection.execute("ALTER TABLE approvals ADD COLUMN position_id TEXT")

    def _ensure_audit_table(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                audit_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                previous_hash TEXT,
                event_hash TEXT NOT NULL UNIQUE
            )
            """
        )

    def _seed_watchlist(self) -> None:
        timestamp = now_iso()
        for index, symbol in enumerate(DEFAULT_WATCHLIST):
            self._connection.execute(
                """
                INSERT OR IGNORE INTO watchlist(symbol, enabled, sort_order, created_at)
                VALUES(?, 1, ?, ?)
                """,
                (symbol, index, timestamp),
            )

    def watchlist(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT symbol, enabled, sort_order, created_at "
                "FROM watchlist ORDER BY sort_order, symbol"
            ).fetchall()
            return [dict(row) for row in rows]

    def replace_watchlist(self, symbols: list[str]) -> list[dict[str, Any]]:
        normalized = [symbol.strip().upper() for symbol in symbols]
        if not normalized or len(set(normalized)) != len(normalized):
            raise ValueError("watchlist must contain at least one unique symbol")
        unsupported = set(normalized) - ALLOWED_SYMBOLS
        if unsupported:
            raise ValueError("only SPY and QQQ are supported in personal V1")
        with self._lock:
            timestamp = now_iso()
            self._connection.execute("DELETE FROM watchlist")
            self._connection.executemany(
                "INSERT INTO watchlist(symbol, enabled, sort_order, created_at) VALUES(?, 1, ?, ?)",
                [(symbol, index, timestamp) for index, symbol in enumerate(normalized)],
            )
        return self.watchlist()

    def create_scan(self, mode: str, symbols: list[str]) -> str:
        scan_id = f"scan_{uuid.uuid4().hex[:20]}"
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO scan_runs(scan_id, mode, status, symbols_json, started_at)
                VALUES(?, ?, 'running', ?, ?)
                """,
                (scan_id, mode, json.dumps(symbols), now_iso()),
            )
        return scan_id

    def finish_scan(
        self, scan_id: str, *, status: str = "completed", error: str | None = None
    ) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE scan_runs SET status = ?, completed_at = ?, error = ? WHERE scan_id = ?",
                (status, now_iso(), error, scan_id),
            )

    def save_decision(
        self,
        *,
        scan_id: str,
        mode: str,
        payload: dict[str, Any],
        status: str = "ready",
    ) -> str:
        decision_id = f"decision_{uuid.uuid4().hex[:20]}"
        case_id = str(payload["case_id"])
        strategy = payload.get("strategy", {})
        verdict = payload.get("verdict", {})
        as_of = str(payload["as_of"])
        freshness_until = (parse_iso(as_of) + timedelta(seconds=30)).isoformat()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO decisions(
                    decision_id, scan_id, case_id, mode, symbol, verdict, status,
                    as_of, freshness_until, maximum_loss, created_at, payload_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    scan_id,
                    case_id,
                    mode,
                    str(payload["underlying_symbol"]),
                    str(verdict.get("decision", "abstain")),
                    status,
                    as_of,
                    freshness_until,
                    str(verdict.get("maximum_loss", strategy.get("maximum_loss", "0"))),
                    now_iso(),
                    json.dumps(payload, sort_keys=True),
                ),
            )
        return decision_id

    def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._decision_row(row) for row in rows]

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
            return None if row is None else self._decision_row(row)

    @staticmethod
    def _decision_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["symbols"] = [result["symbol"]]
        return result

    def mark_decision(self, decision_id: str, status: str) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE decisions SET status = ? WHERE decision_id = ?",
                (status, decision_id),
            )

    def create_approval(self, decision_id: str) -> dict[str, Any]:
        decision = self.get_decision(decision_id)
        if decision is None:
            raise KeyError("decision not found")
        if decision["verdict"] not in {"approve", "resize"}:
            raise ValueError("only approved decisions can be approved for execution")
        payload = decision["payload"]
        if decision["mode"] != "recorded" and parse_iso(
            decision["freshness_until"]
        ) <= datetime.now(UTC):
            raise ValueError("decision snapshot is stale; run a fresh scan")
        verdict = payload["verdict"]
        approval_id = f"approval_{uuid.uuid4().hex[:20]}"
        approved_at = datetime.now(UTC)
        expires_at = approved_at + timedelta(minutes=5)
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO approvals(
                    approval_id, decision_id, kind, position_id, status, approved_at,
                    expires_at, quantity, maximum_loss
                ) VALUES(?, ?, 'entry', NULL, 'prepared', ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    decision_id,
                    approved_at.isoformat(),
                    expires_at.isoformat(),
                    int(verdict["approved_quantity"]),
                    str(verdict["maximum_loss"]),
                ),
            )
            self._connection.execute(
                "UPDATE decisions SET status = 'approval_ready' WHERE decision_id = ?",
                (decision_id,),
            )
        return self.get_approval(approval_id)  # type: ignore[return-value]

    def create_exit_approval(self, position_id: str) -> dict[str, Any]:
        position = next(
            (item for item in self.positions() if item["position_id"] == position_id),
            None,
        )
        if position is None:
            raise KeyError("position not found")
        approval_id = f"approval_{uuid.uuid4().hex[:20]}"
        approved_at = datetime.now(UTC)
        expires_at = approved_at + timedelta(minutes=5)
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO approvals(
                    approval_id, decision_id, kind, position_id, status, approved_at,
                    expires_at, quantity, maximum_loss
                ) VALUES(?, ?, 'exit', ?, 'prepared', ?, ?, 1, '0')
                """,
                (
                    approval_id,
                    position["decision_id"],
                    position_id,
                    approved_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return self.get_approval(approval_id)  # type: ignore[return-value]

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            return None if row is None else dict(row)

    def prepared_exit_approval(self, position_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM approvals
                WHERE position_id = ? AND kind = 'exit' AND status = 'prepared'
                ORDER BY approved_at DESC LIMIT 1
                """,
                (position_id,),
            ).fetchone()
            return None if row is None else dict(row)

    def submit_approval(self, approval_id: str, idempotency_key: str) -> dict[str, Any]:
        if not idempotency_key or len(idempotency_key) > 120:
            raise ValueError("a bounded idempotency key is required")
        with self._lock:
            approval = self.get_approval(approval_id)
            if approval is None:
                raise KeyError("approval not found")
            if approval["status"] == "submitted":
                existing = self._connection.execute(
                    "SELECT * FROM orders WHERE approval_id = ?", (approval_id,)
                ).fetchone()
                if existing is not None:
                    return {"approval": approval, "order": dict(existing), "replayed": True}
            if parse_iso(approval["expires_at"]) <= datetime.now(UTC):
                self._connection.execute(
                    "UPDATE approvals SET status = 'expired' WHERE approval_id = ?",
                    (approval_id,),
                )
                raise ValueError("approval has expired")
            existing_key = self._connection.execute(
                "SELECT * FROM orders WHERE client_order_id = ?", (idempotency_key,)
            ).fetchone()
            if existing_key is not None:
                return {"approval": approval, "order": dict(existing_key), "replayed": True}
            decision = self.get_decision(approval["decision_id"])
            if decision is None:
                raise KeyError("decision not found")
            client_order_id = idempotency_key
            order_id = f"order_{uuid.uuid4().hex[:20]}"
            submitted_at = now_iso()
            safe_reference = f"paper-{hashlib.sha256(order_id.encode()).hexdigest()[:8]}"
            self._connection.execute(
                """
                INSERT INTO orders(
                    order_id, decision_id, approval_id, client_order_id, status,
                    submitted_at, safe_reference
                ) VALUES(?, ?, ?, ?, 'submitted', ?, ?)
                """,
                (
                    order_id,
                    decision["decision_id"],
                    approval_id,
                    client_order_id,
                    submitted_at,
                    safe_reference,
                ),
            )
            self._connection.execute(
                "UPDATE approvals SET status = 'submitted', submitted_at = ?, "
                "idempotency_key = ? WHERE approval_id = ?",
                (submitted_at, idempotency_key, approval_id),
            )
            self._connection.execute(
                "UPDATE decisions SET status = 'submitted' WHERE decision_id = ?",
                (decision["decision_id"],),
            )
            order = self._connection.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
            return {
                "approval": self.get_approval(approval_id),
                "order": dict(order),
                "replayed": False,
            }

    def orders(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM orders ORDER BY submitted_at DESC"
                ).fetchall()
            ]

    def update_order(
        self,
        order_id: str,
        *,
        status: str,
        filled_at: str | None = None,
        filled_debit: str | None = None,
        safe_reference: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._connection.execute(
                """
                UPDATE orders
                SET status = ?, filled_at = ?, filled_debit = ?,
                    safe_reference = COALESCE(?, safe_reference)
                WHERE order_id = ?
                """,
                (status, filled_at, filled_debit, safe_reference, order_id),
            )
            row = self._connection.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
            if row is None:
                raise KeyError("order not found")
            return dict(row)

    def create_position(
        self,
        *,
        decision_id: str,
        order_id: str,
        symbol: str,
        direction: str,
        cost_basis: str,
    ) -> dict[str, Any]:
        with self._lock:
            existing = self._connection.execute(
                "SELECT * FROM positions WHERE order_id = ?", (order_id,)
            ).fetchone()
            if existing is not None:
                return dict(existing)
            position_id = f"position_{uuid.uuid4().hex[:20]}"
            timestamp = now_iso()
            self._connection.execute(
                """
                INSERT INTO positions(
                    position_id, decision_id, order_id, symbol, status, direction,
                    cost_basis, position_value, unrealized_pnl, realized_pnl, updated_at
                ) VALUES(?, ?, ?, ?, 'open', ?, ?, ?, '0', '0', ?)
                """,
                (
                    position_id,
                    decision_id,
                    order_id,
                    symbol,
                    direction,
                    cost_basis,
                    cost_basis,
                    timestamp,
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM positions WHERE position_id = ?", (position_id,)
            ).fetchone()
            return dict(row)

    def update_position(
        self,
        position_id: str,
        *,
        status: str,
        position_value: str,
        unrealized_pnl: str,
        realized_pnl: str,
    ) -> dict[str, Any]:
        with self._lock:
            self._connection.execute(
                """
                UPDATE positions
                SET status = ?, position_value = ?, unrealized_pnl = ?,
                    realized_pnl = ?, updated_at = ?
                WHERE position_id = ?
                """,
                (
                    status,
                    position_value,
                    unrealized_pnl,
                    realized_pnl,
                    now_iso(),
                    position_id,
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM positions WHERE position_id = ?", (position_id,)
            ).fetchone()
            if row is None:
                raise KeyError("position not found")
            return dict(row)

    def positions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM positions ORDER BY updated_at DESC"
                ).fetchall()
            ]

    def journal(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM journal_entries ORDER BY updated_at DESC"
                ).fetchall()
            ]

    def add_journal_entry(self, body: str, decision_id: str | None = None) -> dict[str, Any]:
        clean = body.strip()
        if not clean or len(clean) > 4000:
            raise ValueError("journal body must contain 1 to 4000 characters")
        if decision_id is not None and self.get_decision(decision_id) is None:
            raise ValueError("journal decision reference not found")
        entry_id = f"journal_{uuid.uuid4().hex[:20]}"
        timestamp = now_iso()
        with self._lock:
            self._connection.execute(
                "INSERT INTO journal_entries("
                "entry_id, decision_id, body, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (entry_id, decision_id, clean, timestamp, timestamp),
            )
        return {
            "entry_id": entry_id,
            "decision_id": decision_id,
            "body": clean,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def kill_switch(self) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT enabled, reason, updated_at FROM kill_switch WHERE singleton = 1"
            ).fetchone()
            return {"enabled": bool(row[0]), "reason": row[1], "updated_at": row[2]}

    def set_kill_switch(self, enabled: bool, reason: str = "") -> dict[str, Any]:
        if len(reason) > 240:
            raise ValueError("kill-switch reason is too long")
        with self._lock:
            self._connection.execute(
                "UPDATE kill_switch SET enabled = ?, reason = ?, updated_at = ? "
                "WHERE singleton = 1",
                (int(enabled), reason.strip(), now_iso()),
            )
        return self.kill_switch()

    def record_audit(self, event_type: str, entity_id: str, payload: dict[str, Any]) -> None:
        """Append a sanitized, hash-linked local audit event."""

        occurred_at = now_iso()
        with self._lock:
            previous = self._connection.execute(
                "SELECT event_hash FROM audit_events ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            previous_hash = None if previous is None else previous[0]
            clean_payload = _redact(payload)
            material = json.dumps(
                {
                    "event_type": event_type,
                    "entity_id": entity_id,
                    "payload": clean_payload,
                    "occurred_at": occurred_at,
                    "previous_hash": previous_hash,
                },
                sort_keys=True,
            )
            event_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
            self._connection.execute(
                """
                INSERT OR IGNORE INTO audit_events(
                    audit_id, event_type, entity_id, payload_json, occurred_at,
                    previous_hash, event_hash
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"audit_{event_hash[:20]}",
                    event_type,
                    entity_id,
                    json.dumps(clean_payload, sort_keys=True),
                    occurred_at,
                    previous_hash,
                    event_hash,
                ),
            )

    def audit_history(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM audit_events ORDER BY occurred_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def export_json(self) -> str:
        payload = _redact(
            {
                "watchlist": self.watchlist(),
                "decisions": self.list_decisions(),
                "orders": self.orders(),
                "positions": self.positions(),
                "journal": self.journal(),
                "kill_switch": self.kill_switch(),
                "audit": self.audit_history(),
            }
        )
        return json.dumps(payload, indent=2, sort_keys=True)

    def import_legacy_event_log(self, path: Path) -> int:
        """Import one validated hash-chained JSON log into SQLite audit history."""

        from riskcourt.event_store import PersistentDecisionLog

        log = PersistentDecisionLog(path.stem, path)
        imported = 0
        for chained in log.events:
            event = chained.event
            entity_id = f"{path.stem}:{chained.event_hash}"
            with self._lock:
                exists = self._connection.execute(
                    "SELECT 1 FROM audit_events WHERE entity_id = ?", (entity_id,)
                ).fetchone()
            if exists is not None:
                continue
            self.record_audit(
                f"legacy.{event.event_type.value}",
                entity_id,
                {"case_id": event.case_id, "payload": event.payload},
            )
            imported += 1
        return imported


def _redact(value: Any, key: str | None = None) -> Any:
    if key is not None and any(
        marker in key.lower() for marker in ("secret", "api_key", "account_id", "order_id")
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: _redact(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
