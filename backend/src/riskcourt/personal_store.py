"""Local-first persistence for the RiskCourt personal workstation.

The store deliberately uses the standard-library SQLite driver.  The database
is local application state, while the domain and audit contracts remain owned
by the existing Pydantic models and hash-chained event log.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from riskcourt.risk_limits import PortfolioRiskExposure

DEFAULT_WATCHLIST = ("SPY", "QQQ")
ALLOWED_SYMBOLS = frozenset(DEFAULT_WATCHLIST)
SCHEMA_VERSION = 10
TERMINAL_ORDER_STATUSES = frozenset({"filled", "rejected", "canceled", "cancelled", "expired"})
MAX_OUTCOME_EVIDENCE_BYTES = 1_000_000
MAX_SETTLEMENT_OBSERVATION_AGE = timedelta(minutes=5)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SOURCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
_SOURCE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


def _decision_fingerprint(decision: dict[str, Any]) -> str:
    bound_fields = {
        key: decision[key]
        for key in (
            "decision_id",
            "scan_id",
            "mode",
            "symbol",
            "verdict",
            "as_of",
            "freshness_until",
            "maximum_loss",
            "payload",
        )
    }
    canonical = json.dumps(bound_fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _execute_sql_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute complete statements without sqlite3.executescript's implicit commit."""

    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                connection.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("incomplete personal database migration statement")


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

    def health_check(self) -> dict[str, int | bool]:
        """Check the local database connection and applied schema without mutation."""

        with self._lock:
            self._connection.execute("SELECT 1").fetchone()
            version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            return {"ok": version == SCHEMA_VERSION, "schema_version": version}

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """Serialize a state transition and commit or roll it back as one unit."""

        with self._lock:
            nested = self._connection.in_transaction
            savepoint = f"sp_{uuid.uuid4().hex}"
            self._connection.execute(f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                if nested:
                    self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    self._connection.rollback()
                raise
            else:
                if nested:
                    self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    self._connection.commit()

    def migrate(self) -> None:
        """Apply the immutable local schema migration exactly once."""

        with self._transaction():
            current = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            if current > SCHEMA_VERSION:
                raise RuntimeError("personal database schema is newer than this application")
            if current == 0:
                _execute_sql_script(
                    self._connection,
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
                        client_order_id TEXT UNIQUE,
                        request_sha256 TEXT NOT NULL DEFAULT '',
                        decision_sha256 TEXT NOT NULL DEFAULT '',
                        account_equity TEXT,
                        account_last_equity TEXT,
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
                        request_sha256 TEXT NOT NULL DEFAULT '',
                        filled_qty TEXT NOT NULL DEFAULT '0',
                        accounted_filled_qty TEXT NOT NULL DEFAULT '0',
                        filled_avg_price TEXT,
                        filled_at TEXT,
                        updated_at TEXT,
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
                        quantity TEXT NOT NULL DEFAULT '1',
                        cost_basis TEXT NOT NULL,
                        position_value TEXT NOT NULL,
                        unrealized_pnl TEXT NOT NULL,
                        realized_pnl TEXT NOT NULL,
                        mark_at TEXT,
                        reconciliation_status TEXT NOT NULL DEFAULT 'unverified',
                        reconciliation_reason TEXT NOT NULL DEFAULT '',
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
                    CREATE TABLE IF NOT EXISTS daily_equity_baseline (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        trading_day TEXT NOT NULL,
                        broker_last_equity TEXT NOT NULL,
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
                    PRAGMA user_version = 10;
                    """
                )
                self._create_forecast_schema()
                self._seed_watchlist()
            else:
                if current == 1:
                    order_columns = {
                        row[1]
                        for row in self._connection.execute("PRAGMA table_info(orders)").fetchall()
                    }
                    if "request_sha256" not in order_columns:
                        self._connection.execute(
                            "ALTER TABLE orders ADD COLUMN request_sha256 TEXT NOT NULL DEFAULT ''"
                        )
                    current = 2
                if current == 2:
                    approval_columns = {
                        row[1]
                        for row in self._connection.execute(
                            "PRAGMA table_info(approvals)"
                        ).fetchall()
                    }
                    if "client_order_id" not in approval_columns:
                        self._connection.execute(
                            "ALTER TABLE approvals ADD COLUMN client_order_id TEXT"
                        )
                    if "request_sha256" not in approval_columns:
                        self._connection.execute(
                            "ALTER TABLE approvals ADD COLUMN "
                            "request_sha256 TEXT NOT NULL DEFAULT ''"
                        )
                    self._connection.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_client_order_id "
                        "ON approvals(client_order_id) WHERE client_order_id IS NOT NULL"
                    )
                    current = 3
                if current == 3:
                    approval_columns = {
                        row[1]
                        for row in self._connection.execute(
                            "PRAGMA table_info(approvals)"
                        ).fetchall()
                    }
                    if "account_equity" not in approval_columns:
                        self._connection.execute(
                            "ALTER TABLE approvals ADD COLUMN account_equity TEXT"
                        )
                    if "account_last_equity" not in approval_columns:
                        self._connection.execute(
                            "ALTER TABLE approvals ADD COLUMN account_last_equity TEXT"
                        )
                    current = 4
                if current == 4:
                    order_columns = {
                        row[1]
                        for row in self._connection.execute("PRAGMA table_info(orders)").fetchall()
                    }
                    for name, declaration in (
                        ("filled_qty", "TEXT NOT NULL DEFAULT '0'"),
                        ("filled_avg_price", "TEXT"),
                        ("updated_at", "TEXT"),
                    ):
                        if name not in order_columns:
                            self._connection.execute(
                                f"ALTER TABLE orders ADD COLUMN {name} {declaration}"
                            )
                    position_columns = {
                        row[1]
                        for row in self._connection.execute(
                            "PRAGMA table_info(positions)"
                        ).fetchall()
                    }
                    for name, declaration in (
                        ("quantity", "TEXT NOT NULL DEFAULT '1'"),
                        ("mark_at", "TEXT"),
                    ):
                        if name not in position_columns:
                            self._connection.execute(
                                f"ALTER TABLE positions ADD COLUMN {name} {declaration}"
                            )
                    current = 5
                if current == 5:
                    order_columns = {
                        row[1]
                        for row in self._connection.execute("PRAGMA table_info(orders)").fetchall()
                    }
                    if "accounted_filled_qty" not in order_columns:
                        self._connection.execute(
                            "ALTER TABLE orders ADD COLUMN "
                            "accounted_filled_qty TEXT NOT NULL DEFAULT '0'"
                        )
                    current = 6
                if current == 6:
                    position_columns = {
                        row[1]
                        for row in self._connection.execute(
                            "PRAGMA table_info(positions)"
                        ).fetchall()
                    }
                    for name, declaration in (
                        ("reconciliation_status", "TEXT NOT NULL DEFAULT 'unverified'"),
                        ("reconciliation_reason", "TEXT NOT NULL DEFAULT ''"),
                    ):
                        if name not in position_columns:
                            self._connection.execute(
                                f"ALTER TABLE positions ADD COLUMN {name} {declaration}"
                            )
                    current = 7
                if current == 7:
                    approval_columns = {
                        row[1]
                        for row in self._connection.execute(
                            "PRAGMA table_info(approvals)"
                        ).fetchall()
                    }
                    if "decision_sha256" not in approval_columns:
                        self._connection.execute(
                            "ALTER TABLE approvals ADD COLUMN "
                            "decision_sha256 TEXT NOT NULL DEFAULT ''"
                        )
                    current = 8
                if current == 8:
                    self._connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS daily_equity_baseline (
                            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                            trading_day TEXT NOT NULL,
                            broker_last_equity TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                        """
                    )
                    current = 9
                if current == 9:
                    self._create_forecast_schema()
                    current = 10
                self._connection.execute(f"PRAGMA user_version = {current}")
            self._ensure_approval_columns()
            self._ensure_audit_table()

    def _create_forecast_schema(self) -> None:
        """Create append-only forecast and outcome evidence tables."""

        _execute_sql_script(
            self._connection,
            """
            CREATE TABLE IF NOT EXISTS forecast_observations (
                decision_id TEXT NOT NULL,
                forecast_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('recorded', 'paper')),
                symbol TEXT NOT NULL CHECK(symbol IN ('SPY', 'QQQ')),
                juror_id TEXT NOT NULL,
                forecast_outcome TEXT NOT NULL CHECK(
                    forecast_outcome IN ('above_strike', 'below_strike')
                ),
                probability TEXT NOT NULL,
                calibration_score TEXT NOT NULL,
                calibration_version TEXT NOT NULL,
                confidence_stake TEXT NOT NULL,
                provider_quality TEXT,
                evidence_count INTEGER NOT NULL CHECK(evidence_count >= 0),
                produced_at TEXT NOT NULL,
                horizon_at TEXT NOT NULL,
                model_version TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                provider_mode TEXT NOT NULL,
                simulated INTEGER NOT NULL CHECK(simulated IN (0, 1)),
                event_contract_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(decision_id, forecast_id),
                FOREIGN KEY(decision_id) REFERENCES decisions(decision_id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_forecast_observations_group
                ON forecast_observations(juror_id, model_version, prompt_version, produced_at);
            CREATE TABLE IF NOT EXISTS outcome_evidence (
                sha256 TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content BLOB NOT NULL,
                imported_at TEXT NOT NULL,
                CHECK(length(sha256) = 64)
            );
            CREATE TABLE IF NOT EXISTS forecast_outcomes (
                decision_id TEXT PRIMARY KEY,
                observed_at TEXT NOT NULL,
                settlement_price TEXT NOT NULL,
                realized INTEGER NOT NULL CHECK(realized IN (0, 1)),
                source_name TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                evidence_sha256 TEXT NOT NULL,
                event_contract_sha256 TEXT NOT NULL,
                resolved_at TEXT NOT NULL,
                FOREIGN KEY(decision_id) REFERENCES decisions(decision_id) ON DELETE RESTRICT,
                FOREIGN KEY(evidence_sha256) REFERENCES outcome_evidence(sha256) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_resolved
                ON forecast_outcomes(resolved_at, decision_id);
            CREATE TRIGGER IF NOT EXISTS forecast_observations_no_update
            BEFORE UPDATE ON forecast_observations BEGIN
                SELECT RAISE(ABORT, 'forecast observations are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS forecast_observations_no_delete
            BEFORE DELETE ON forecast_observations BEGIN
                SELECT RAISE(ABORT, 'forecast observations are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS forecast_outcomes_no_update
            BEFORE UPDATE ON forecast_outcomes BEGIN
                SELECT RAISE(ABORT, 'forecast outcomes are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS forecast_outcomes_no_delete
            BEFORE DELETE ON forecast_outcomes BEGIN
                SELECT RAISE(ABORT, 'forecast outcomes are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS outcome_evidence_no_update
            BEFORE UPDATE ON outcome_evidence BEGIN
                SELECT RAISE(ABORT, 'outcome evidence is immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS outcome_evidence_no_delete
            BEFORE DELETE ON outcome_evidence BEGIN
                SELECT RAISE(ABORT, 'outcome evidence is immutable');
            END;
            """,
        )

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
        with self._transaction():
            timestamp = now_iso()
            self._connection.execute("DELETE FROM watchlist")
            self._connection.executemany(
                "INSERT INTO watchlist(symbol, enabled, sort_order, created_at) VALUES(?, 1, ?, ?)",
                [(symbol, index, timestamp) for index, symbol in enumerate(normalized)],
            )
            self.record_audit("watchlist.updated", "watchlist", {"symbols": normalized})
        return self.watchlist()

    def create_scan(self, mode: str, symbols: list[str]) -> str:
        scan_id = f"scan_{uuid.uuid4().hex[:20]}"
        with self._transaction():
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
        with self._transaction():
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
        with self._transaction():
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
            self._persist_forecast_observations(decision_id, mode, payload)
        return decision_id

    def _persist_forecast_observations(
        self, decision_id: str, mode: str, payload: dict[str, Any]
    ) -> None:
        forecasts = payload.get("forecasts")
        event = payload.get("forecast_event")
        if not isinstance(forecasts, list) or not forecasts:
            return
        if not isinstance(event, dict):
            if mode == "paper":
                raise ValueError("paper forecasts require a persisted event contract")
            return

        event_fields = (
            "symbol",
            "threshold",
            "condition",
            "horizon_at",
            "settlement_rule",
            "calendar_source",
            "role_mode",
            "minimum_quorum",
        )
        contract = {key: event[key] for key in event_fields if key in event}
        required_fields = set(event_fields[:6])
        if not required_fields.issubset(contract):
            raise ValueError("forecast event contract is incomplete")
        if contract["symbol"] != payload.get("underlying_symbol"):
            raise ValueError("forecast event symbol does not match its decision")
        if contract["symbol"] not in ALLOWED_SYMBOLS:
            raise ValueError("forecast event symbol is unsupported")
        if contract["condition"] not in {
            "underlying_price_above_threshold",
            "underlying_price_at_or_below_threshold",
        }:
            raise ValueError("forecast event condition is unsupported")
        try:
            threshold = Decimal(str(contract["threshold"]))
            horizon_at = parse_iso(str(contract["horizon_at"]))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("forecast event threshold or horizon is invalid") from error
        if not threshold.is_finite() or threshold <= 0:
            raise ValueError("forecast event threshold must be positive")
        contract_json = json.dumps(contract, sort_keys=True, separators=(",", ":"))
        provider = payload.get("provider")
        provider = provider if isinstance(provider, dict) else {}
        provider_mode = str(provider.get("mode", "unknown"))[:40]
        simulated = bool(provider.get("simulated", False))
        case_id = str(payload.get("case_id", ""))
        persisted: list[tuple[Any, ...]] = []
        seen_forecasts: set[str] = set()
        for forecast in forecasts:
            if not isinstance(forecast, dict):
                raise ValueError("forecast entry must be an object")
            try:
                forecast_id = str(forecast["forecast_id"])
                juror_id = str(forecast["juror_id"])
                forecast_case_id = str(forecast["case_id"])
                forecast_outcome = str(forecast["outcome"])
                probability = Decimal(str(forecast["probability"]))
                calibration_score = Decimal(str(forecast["calibration_score"]))
                confidence_stake = Decimal(str(forecast["confidence_stake"]))
                produced_at = parse_iso(str(forecast["produced_at"]))
                forecast_horizon = parse_iso(str(forecast["horizon_at"]))
                model_version = str(forecast["model_version"])
                prompt_version = str(forecast["prompt_version"])
                evidence_ids = forecast.get("evidence_ids", [])
                provider_metadata = forecast.get("provider_metadata", {})
            except (KeyError, InvalidOperation, TypeError, ValueError) as error:
                raise ValueError("forecast entry is missing valid contract fields") from error
            if not forecast_id or forecast_id in seen_forecasts or not juror_id:
                raise ValueError("forecast IDs must be unique within a decision")
            seen_forecasts.add(forecast_id)
            if forecast_case_id != case_id or forecast_horizon != horizon_at:
                raise ValueError("forecast does not match its event contract")
            if produced_at >= horizon_at:
                raise ValueError("forecast must be produced before its event horizon")
            if forecast_outcome not in {"above_strike", "below_strike"}:
                raise ValueError("forecast outcome is unsupported")
            expected_outcome = (
                "above_strike"
                if contract["condition"] == "underlying_price_above_threshold"
                else "below_strike"
            )
            if forecast_outcome != expected_outcome:
                raise ValueError("forecast direction does not match its event contract")
            if any(
                not value.is_finite() or value < 0 or value > 1
                for value in (probability, calibration_score, confidence_stake)
            ):
                raise ValueError("forecast probabilities and stakes must be between 0 and 1")
            if not model_version or len(model_version) > 120:
                raise ValueError("forecast model version is invalid")
            if not prompt_version or len(prompt_version) > 120:
                raise ValueError("forecast prompt version is invalid")
            if not isinstance(evidence_ids, list) or any(
                not isinstance(item, str) for item in evidence_ids
            ):
                raise ValueError("forecast evidence IDs must be a list of strings")
            if not isinstance(provider_metadata, dict):
                raise ValueError("forecast provider metadata must be an object")
            quality_value = provider_metadata.get("evidence_quality")
            provider_quality: str | None = None
            if quality_value is not None:
                try:
                    quality = Decimal(str(quality_value))
                except InvalidOperation as error:
                    raise ValueError("provider evidence quality is invalid") from error
                if not quality.is_finite() or quality < 0 or quality > 1:
                    raise ValueError("provider evidence quality must be between 0 and 1")
                provider_quality = str(quality)
            calibration_version = str(
                provider_metadata.get("calibration_basis", "configured_prior_v1")
            )[:80]
            persisted.append(
                (
                    decision_id,
                    forecast_id,
                    case_id,
                    mode,
                    contract["symbol"],
                    juror_id,
                    forecast_outcome,
                    str(probability),
                    str(calibration_score),
                    calibration_version,
                    str(confidence_stake),
                    provider_quality,
                    len(evidence_ids),
                    produced_at.isoformat(),
                    horizon_at.isoformat(),
                    model_version,
                    prompt_version,
                    provider_mode,
                    int(simulated),
                    contract_json,
                    now_iso(),
                )
            )
        self._connection.executemany(
            """
            INSERT INTO forecast_observations(
                decision_id, forecast_id, case_id, mode, symbol, juror_id,
                forecast_outcome, probability, calibration_score, calibration_version,
                confidence_stake, provider_quality, evidence_count, produced_at,
                horizon_at, model_version, prompt_version, provider_mode, simulated,
                event_contract_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            persisted,
        )
        contract_digest = hashlib.sha256(contract_json.encode("utf-8")).hexdigest()
        self.record_audit(
            "forecast.contract_persisted",
            decision_id,
            {"forecast_count": len(persisted), "event_contract_sha256": contract_digest},
        )

    def resolve_forecast_outcomes(
        self,
        resolutions: list[dict[str, str]],
        *,
        evidence_filename: str,
        evidence_bytes: bytes,
        resolved_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve stored event contracts from one immutable, hashed evidence dataset."""

        if not resolutions or len(resolutions) > 1000:
            raise ValueError("outcome import must contain between 1 and 1000 rows")
        if len(evidence_bytes) > MAX_OUTCOME_EVIDENCE_BYTES or not evidence_bytes:
            raise ValueError("outcome evidence file must contain 1 to 1,000,000 bytes")
        if not _EVIDENCE_NAME_PATTERN.fullmatch(evidence_filename):
            raise ValueError("outcome evidence filename is invalid")
        digest = hashlib.sha256(evidence_bytes).hexdigest()
        if resolved_at is None:
            imported_at = datetime.now(UTC)
        elif resolved_at.tzinfo is None or resolved_at.utcoffset() is None:
            raise ValueError("outcome resolution timestamp must be timezone-aware")
        else:
            imported_at = resolved_at.astimezone(UTC)
        decision_ids = [str(row.get("decision_id", "")) for row in resolutions]
        if any(not decision_id for decision_id in decision_ids) or len(set(decision_ids)) != len(
            decision_ids
        ):
            raise ValueError("outcome import decision IDs must be nonempty and unique")

        normalized: list[dict[str, Any]] = []
        for row in resolutions:
            if set(row) != {
                "decision_id",
                "observed_at",
                "settlement_price",
                "source_name",
                "source_reference",
            }:
                raise ValueError("outcome row has missing or unexpected fields")
            source_name = row["source_name"]
            source_reference = row["source_reference"]
            if not _SOURCE_NAME_PATTERN.fullmatch(source_name):
                raise ValueError("outcome source name is invalid")
            if (
                not _SOURCE_REFERENCE_PATTERN.fullmatch(source_reference)
                or "://" in source_reference
            ):
                raise ValueError("outcome source reference must be a sanitized opaque ID")
            try:
                observed_at = parse_iso(row["observed_at"]).astimezone(UTC)
                settlement_price = Decimal(row["settlement_price"])
            except (InvalidOperation, TypeError, ValueError) as error:
                raise ValueError("outcome timestamp or settlement price is invalid") from error
            if not settlement_price.is_finite() or settlement_price <= 0:
                raise ValueError("settlement price must be a positive finite number")
            normalized.append(
                {
                    **row,
                    "observed_at": observed_at,
                    "settlement_price": settlement_price,
                }
            )

        results: list[dict[str, Any]] = []
        with self._transaction():
            existing_evidence = self._connection.execute(
                "SELECT content FROM outcome_evidence WHERE sha256 = ?", (digest,)
            ).fetchone()
            if existing_evidence is None:
                self._connection.execute(
                    """
                    INSERT INTO outcome_evidence(sha256, filename, content, imported_at)
                    VALUES(?, ?, ?, ?)
                    """,
                    (
                        digest,
                        evidence_filename,
                        sqlite3.Binary(evidence_bytes),
                        imported_at.isoformat(),
                    ),
                )
            elif bytes(existing_evidence["content"]) != evidence_bytes:
                raise ValueError("outcome evidence hash collision")

            for normalized_row in normalized:
                decision_id = str(normalized_row["decision_id"])
                forecasts = self._connection.execute(
                    "SELECT * FROM forecast_observations WHERE decision_id = ?",
                    (decision_id,),
                ).fetchall()
                if not forecasts:
                    raise KeyError("decision has no persisted forecast event contract")
                if self._connection.execute(
                    "SELECT 1 FROM forecast_outcomes WHERE decision_id = ?", (decision_id,)
                ).fetchone():
                    raise ValueError("forecast outcome is already resolved and immutable")
                contracts = {str(forecast["event_contract_json"]) for forecast in forecasts}
                if len(contracts) != 1:
                    raise ValueError("forecast rows do not share one event contract")
                contract_json = contracts.pop()
                contract = json.loads(contract_json)
                horizon_at = parse_iso(str(contract["horizon_at"])).astimezone(UTC)
                observed_at = normalized_row["observed_at"]
                if imported_at < horizon_at:
                    raise ValueError("forecast horizon has not elapsed")
                if observed_at > horizon_at or observed_at < (
                    horizon_at - MAX_SETTLEMENT_OBSERVATION_AGE
                ):
                    raise ValueError(
                        "settlement observation must be within five minutes before horizon"
                    )
                if any(
                    parse_iso(str(forecast["produced_at"])).astimezone(UTC) >= observed_at
                    for forecast in forecasts
                ):
                    raise ValueError("settlement observation must follow every forecast")
                threshold = Decimal(str(contract["threshold"]))
                price = normalized_row["settlement_price"]
                condition = contract["condition"]
                realized = (
                    price > threshold
                    if condition == "underlying_price_above_threshold"
                    else price <= threshold
                )
                contract_digest = hashlib.sha256(contract_json.encode("utf-8")).hexdigest()
                self._connection.execute(
                    """
                    INSERT INTO forecast_outcomes(
                        decision_id, observed_at, settlement_price, realized, source_name,
                        source_reference, evidence_sha256, event_contract_sha256, resolved_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision_id,
                        observed_at.isoformat(),
                        str(price),
                        int(realized),
                        normalized_row["source_name"],
                        normalized_row["source_reference"],
                        digest,
                        contract_digest,
                        imported_at.isoformat(),
                    ),
                )
                outcome = {
                    "decision_id": decision_id,
                    "observed_at": observed_at.isoformat(),
                    "settlement_price": str(price),
                    "realized": realized,
                    "source_name": normalized_row["source_name"],
                    "source_reference": normalized_row["source_reference"],
                    "evidence_sha256": digest,
                    "event_contract_sha256": contract_digest,
                    "resolved_at": imported_at.isoformat(),
                }
                self.record_audit(
                    "forecast.outcome_resolved",
                    decision_id,
                    {
                        "realized": realized,
                        "source_name": normalized_row["source_name"],
                        "source_reference": normalized_row["source_reference"],
                        "evidence_sha256": digest,
                        "event_contract_sha256": contract_digest,
                    },
                )
                results.append(outcome)
        return results

    def resolved_forecast_samples(
        self, *, include_simulated: bool = False, mode: str | None = None
    ) -> list[dict[str, Any]]:
        """Return resolved forecast rows without exposing the underlying evidence file."""

        conditions = ["fo.simulated = 0"] if not include_simulated else []
        parameters: list[Any] = []
        if mode is not None:
            if mode not in {"recorded", "paper"}:
                raise ValueError("forecast mode is invalid")
            conditions.append("fo.mode = ?")
            parameters.append(mode)
        where = " AND ".join(conditions)
        if where:
            where = f"WHERE {where}"
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT fo.decision_id, fo.forecast_id, fo.mode, fo.provider_mode,
                       fo.juror_id, fo.probability,
                       fo.calibration_score, fo.calibration_version, fo.confidence_stake,
                       fo.provider_quality, fo.evidence_count, fo.produced_at, fo.horizon_at,
                       fo.model_version, fo.prompt_version, fo.provider_mode, fo.simulated,
                       o.realized, o.resolved_at, o.observed_at, o.source_name,
                       o.evidence_sha256
                FROM forecast_observations AS fo
                JOIN forecast_outcomes AS o USING(decision_id)
                {where}
                ORDER BY fo.produced_at, fo.decision_id, fo.forecast_id
                """,
                parameters,
            ).fetchall()
            return [dict(row) for row in rows]

    def pending_forecast_events(self) -> list[dict[str, Any]]:
        """List unresolved event contracts without exposing broker evidence IDs."""

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT fo.decision_id, fo.mode, fo.symbol, fo.event_contract_json,
                       COUNT(*) AS forecast_count, MIN(fo.produced_at) AS first_forecast_at,
                       MAX(fo.produced_at) AS last_forecast_at
                FROM forecast_observations AS fo
                LEFT JOIN forecast_outcomes AS outcome USING(decision_id)
                WHERE outcome.decision_id IS NULL
                GROUP BY fo.decision_id, fo.mode, fo.symbol, fo.event_contract_json
                ORDER BY fo.event_contract_json, fo.decision_id
                """
            ).fetchall()
            return [
                {
                    "decision_id": row["decision_id"],
                    "mode": row["mode"],
                    "symbol": row["symbol"],
                    "event_contract": json.loads(row["event_contract_json"]),
                    "forecast_count": int(row["forecast_count"]),
                    "first_forecast_at": row["first_forecast_at"],
                    "last_forecast_at": row["last_forecast_at"],
                }
                for row in rows
            ]

    def list_decisions(self, limit: int = 50, *, mode: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if mode is None:
                rows = self._connection.execute(
                    "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM decisions WHERE mode = ? ORDER BY created_at DESC LIMIT ?",
                    (mode, limit),
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

    def create_approval(
        self,
        decision_id: str,
        *,
        approval_id: str | None = None,
        client_order_id: str | None = None,
        request_sha256: str | None = None,
        account_equity: str | None = None,
        account_last_equity: str | None = None,
    ) -> dict[str, Any]:
        has_binding = client_order_id is not None and request_sha256 is not None
        if (client_order_id is None) != (request_sha256 is None):
            raise ValueError("client order ID and request fingerprint must be bound together")
        if (account_equity is None) != (account_last_equity is None):
            raise ValueError("current and prior account equity must be bound together")
        if client_order_id is not None and (not client_order_id or len(client_order_id) > 48):
            raise ValueError("client_order_id must contain 1 to 48 characters")
        if request_sha256 is not None and (
            len(request_sha256) != 64
            or any(char not in "0123456789abcdef" for char in request_sha256)
        ):
            raise ValueError("request fingerprint must be a lowercase SHA-256 digest")
        with self._transaction():
            decision = self.get_decision(decision_id)
            if decision is None:
                raise KeyError("decision not found")
            if decision["mode"] == "paper" and (not has_binding or account_equity is None):
                raise ValueError("paper approval must bind its exact order and account state")
            if decision["mode"] == "paper":
                account_payload = decision["payload"].get("account", {}).get("account", {})
                try:
                    bound_equity = Decimal(str(account_equity))
                    bound_last_equity = Decimal(str(account_last_equity))
                    payload_equity = Decimal(str(account_payload["equity"]))
                    payload_last_equity = Decimal(str(account_payload["last_equity"]))
                except (KeyError, InvalidOperation, TypeError) as error:
                    raise ValueError("paper decision has no valid equity evidence") from error
                if (
                    not bound_equity.is_finite()
                    or not bound_last_equity.is_finite()
                    or bound_equity <= 0
                    or bound_last_equity <= 0
                    or bound_equity != payload_equity
                    or bound_last_equity != payload_last_equity
                ):
                    raise ValueError("paper approval equity must match its decision snapshot")
            if decision["status"] == "vetoed":
                raise ValueError("vetoed decisions cannot be approved")
            if decision["status"] not in {"ready", "approval_ready"}:
                raise ValueError("decision is not eligible for an entry approval")
            if decision["verdict"] not in {"approve", "resize"}:
                raise ValueError("only approved decisions can be approved for execution")

            now = datetime.now(UTC)
            payload = decision["payload"]
            if decision["mode"] != "recorded" and parse_iso(decision["freshness_until"]) <= now:
                raise ValueError("decision snapshot is stale; run a fresh scan")

            active = self._connection.execute(
                """
                SELECT * FROM approvals
                WHERE decision_id = ? AND kind = 'entry' AND status = 'prepared'
                ORDER BY approved_at DESC LIMIT 1
                """,
                (decision_id,),
            ).fetchone()
            if active is not None:
                if parse_iso(active["expires_at"]) > now:
                    return dict(active)
                self._connection.execute(
                    "UPDATE approvals SET status = 'expired' WHERE approval_id = ?",
                    (active["approval_id"],),
                )

            reserved = self._connection.execute(
                """
                SELECT 1 FROM approvals
                WHERE decision_id = ? AND kind = 'entry'
                    AND status IN ('submitting', 'unknown', 'submitted')
                LIMIT 1
                """,
                (decision_id,),
            ).fetchone()
            if reserved is not None:
                raise ValueError("decision already has a submitted entry approval")

            verdict = payload["verdict"]
            resolved_approval_id = approval_id or f"approval_{uuid.uuid4().hex[:20]}"
            approved_at = now
            expires_at = approved_at + timedelta(minutes=5)
            self._connection.execute(
                """
                INSERT INTO approvals(
                    approval_id, decision_id, kind, position_id, status, approved_at,
                    expires_at, quantity, maximum_loss, client_order_id, request_sha256,
                    decision_sha256, account_equity, account_last_equity
                ) VALUES(?, ?, 'entry', NULL, 'prepared', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_approval_id,
                    decision_id,
                    approved_at.isoformat(),
                    expires_at.isoformat(),
                    int(verdict["approved_quantity"]),
                    str(verdict["maximum_loss"]),
                    client_order_id,
                    request_sha256 or "",
                    _decision_fingerprint(decision),
                    account_equity,
                    account_last_equity,
                ),
            )
            updated = self._connection.execute(
                "UPDATE decisions SET status = 'approval_ready' "
                "WHERE decision_id = ? AND status IN ('ready', 'approval_ready')",
                (decision_id,),
            )
            if updated.rowcount != 1:
                raise ValueError("decision state changed before approval")
            self.record_audit(
                "decision.approved",
                decision_id,
                {"approval_id": resolved_approval_id},
            )
            return self.get_approval(resolved_approval_id)  # type: ignore[return-value]

    def veto_decision(self, decision_id: str) -> dict[str, Any]:
        """Veto an unsubmitted decision and revoke its prepared entry approvals."""

        with self._transaction():
            decision = self.get_decision(decision_id)
            if decision is None:
                raise KeyError("decision not found")
            if decision["status"] == "vetoed":
                return decision
            if decision["status"] == "submitted":
                raise ValueError("submitted decisions cannot be vetoed")
            if decision["status"] not in {"ready", "approval_ready"}:
                raise ValueError("decision is not in a vetoable state")
            existing_order = self._connection.execute(
                "SELECT 1 FROM orders WHERE decision_id = ? LIMIT 1", (decision_id,)
            ).fetchone()
            if existing_order is not None:
                raise ValueError("submitted decisions cannot be vetoed")

            updated = self._connection.execute(
                "UPDATE decisions SET status = 'vetoed' "
                "WHERE decision_id = ? AND status IN ('ready', 'approval_ready')",
                (decision_id,),
            )
            if updated.rowcount != 1:
                raise ValueError("decision state changed before veto")
            self._connection.execute(
                "UPDATE approvals SET status = 'revoked' "
                "WHERE decision_id = ? AND kind = 'entry' AND status = 'prepared'",
                (decision_id,),
            )
            self.record_audit("decision.vetoed", decision_id, {})
            return self.get_decision(decision_id) or decision

    def create_exit_approval(
        self,
        position_id: str,
        *,
        approval_id: str,
        client_order_id: str,
        request_sha256: str,
    ) -> dict[str, Any]:
        if not approval_id or not client_order_id or len(client_order_id) > 48:
            raise ValueError("exit approval and client order IDs must be bounded")
        if len(request_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in request_sha256
        ):
            raise ValueError("request fingerprint must be a lowercase SHA-256 digest")
        with self._transaction():
            position = self._connection.execute(
                "SELECT * FROM positions WHERE position_id = ?", (position_id,)
            ).fetchone()
            if position is None:
                raise KeyError("position not found")
            if position["status"] != "open":
                raise ValueError("only open positions can be approved for exit")
            decision = self.get_decision(position["decision_id"])
            if decision is None:
                raise ValueError("position entry decision is missing")
            active = self._connection.execute(
                """SELECT * FROM approvals WHERE position_id = ? AND kind = 'exit'
                    AND status IN ('prepared', 'submitting', 'unknown', 'submitted',
                    'partially_filled') ORDER BY approved_at DESC LIMIT 1""",
                (position_id,),
            ).fetchone()
            if active is not None:
                if active["status"] != "prepared":
                    raise ValueError("an exit order is already pending reconciliation")
                if active["request_sha256"] == request_sha256:
                    return dict(active)
                self._connection.execute(
                    "UPDATE approvals SET status = 'expired' WHERE approval_id = ?",
                    (active["approval_id"],),
                )
            approved_at = datetime.now(UTC)
            expires_at = approved_at + timedelta(minutes=5)
            self._connection.execute(
                """
                INSERT INTO approvals(
                    approval_id, decision_id, kind, position_id, status, approved_at,
                    expires_at, quantity, maximum_loss, client_order_id, request_sha256,
                    decision_sha256
                ) VALUES(?, ?, 'exit', ?, 'prepared', ?, ?, ?, '0', ?, ?, ?)
                """,
                (
                    approval_id,
                    position["decision_id"],
                    position_id,
                    approved_at.isoformat(),
                    expires_at.isoformat(),
                    int(Decimal(position["quantity"])),
                    client_order_id,
                    request_sha256,
                    _decision_fingerprint(decision),
                ),
            )
            self.record_audit(
                "position.exit_approved",
                position_id,
                {"approval_id": approval_id},
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

    def expire_prepared_approval(self, approval_id: str, *, reason: str) -> None:
        with self._transaction():
            updated = self._connection.execute(
                "UPDATE approvals SET status = 'expired' "
                "WHERE approval_id = ? AND status = 'prepared'",
                (approval_id,),
            )
            if updated.rowcount == 1:
                self.record_audit(
                    "approval.expired",
                    approval_id,
                    {"reason": reason[:120]},
                )

    def reserve_approval_submission(
        self,
        approval_id: str,
        client_order_id: str,
        request_sha256: str,
    ) -> dict[str, Any]:
        if not client_order_id or len(client_order_id) > 48:
            raise ValueError("client_order_id must contain 1 to 48 characters")
        if len(request_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in request_sha256
        ):
            raise ValueError("request fingerprint must be a lowercase SHA-256 digest")
        expired = False
        submission: dict[str, Any] | None = None
        with self._transaction():
            approval = self.get_approval(approval_id)
            if approval is None:
                raise KeyError("approval not found")
            existing = self._connection.execute(
                "SELECT * FROM orders WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            if existing is not None:
                if not existing["request_sha256"]:
                    raise ValueError(
                        "legacy order has no request fingerprint and cannot be retried safely"
                    )
                if existing["request_sha256"] != request_sha256:
                    raise ValueError("approval is already bound to a different order request")
                if existing["status"] == "rejected":
                    raise ValueError(
                        "paper order was rejected; prepare a new decision and approval"
                    )
                return {"approval": approval, "order": dict(existing), "replayed": True}
            if approval["status"] != "prepared":
                raise ValueError(f"{approval['status']} approval cannot be submitted")
            expired = parse_iso(approval["expires_at"]) <= datetime.now(UTC)
            if expired:
                self._connection.execute(
                    "UPDATE approvals SET status = 'expired' WHERE approval_id = ?",
                    (approval_id,),
                )
            else:
                decision = self.get_decision(approval["decision_id"])
                if decision is None:
                    raise KeyError("decision not found")
                if approval["kind"] == "entry":
                    if decision["mode"] != "paper":
                        raise ValueError("recorded decisions cannot submit paper orders")
                    if decision["status"] != "approval_ready":
                        raise ValueError("entry decision is vetoed or no longer approval-ready")
                    if parse_iso(decision["freshness_until"]) <= datetime.now(UTC):
                        raise ValueError("decision snapshot is stale; run a fresh scan")
                    if (
                        approval["client_order_id"] != client_order_id
                        or approval["request_sha256"] != request_sha256
                    ):
                        raise ValueError("order request does not match the approved request")
                    if approval["decision_sha256"] != _decision_fingerprint(decision):
                        raise ValueError("decision evidence or policy changed after approval")
                    if int(approval["quantity"]) != int(
                        decision["payload"]["verdict"]["approved_quantity"]
                    ) or Decimal(approval["maximum_loss"]) != Decimal(decision["maximum_loss"]):
                        raise ValueError("approved size or maximum loss no longer matches")
                    if (
                        approval["account_equity"] is None
                        or approval["account_last_equity"] is None
                    ):
                        raise ValueError("paper approval has no bound account snapshot")
                    kill_switch = self._connection.execute(
                        "SELECT enabled FROM kill_switch WHERE singleton = 1"
                    ).fetchone()
                    if kill_switch is None or bool(kill_switch["enabled"]):
                        raise ValueError("kill switch blocks new entries")
                elif approval["kind"] == "exit":
                    if decision["mode"] != "paper":
                        raise ValueError("recorded positions cannot submit paper exits")
                    if (
                        approval["client_order_id"] != client_order_id
                        or approval["request_sha256"] != request_sha256
                        or approval["decision_sha256"] != _decision_fingerprint(decision)
                    ):
                        raise ValueError("exit order differs from the approved position")
                    position = self._connection.execute(
                        "SELECT status, quantity FROM positions WHERE position_id = ?",
                        (approval["position_id"],),
                    ).fetchone()
                    if (
                        position is None
                        or position["status"] != "open"
                        or Decimal(position["quantity"]) != Decimal(approval["quantity"])
                    ):
                        raise ValueError("position changed after exit approval")
                conflicting_id = self._connection.execute(
                    "SELECT approval_id FROM orders WHERE client_order_id = ?",
                    (client_order_id,),
                ).fetchone()
                if conflicting_id is not None:
                    raise ValueError("client_order_id is already bound to another approval")
                assert decision is not None
                order_id = f"order_{uuid.uuid4().hex[:20]}"
                submitted_at = now_iso()
                safe_reference = f"paper-{hashlib.sha256(order_id.encode()).hexdigest()[:8]}"
                self._connection.execute(
                    """
                    INSERT INTO orders(
                        order_id, decision_id, approval_id, client_order_id, status,
                        submitted_at, request_sha256, safe_reference
                    ) VALUES(?, ?, ?, ?, 'submitting', ?, ?, ?)
                    """,
                    (
                        order_id,
                        decision["decision_id"],
                        approval_id,
                        client_order_id,
                        submitted_at,
                        request_sha256,
                        safe_reference,
                    ),
                )
                updated = self._connection.execute(
                    "UPDATE approvals SET status = 'submitting', submitted_at = ? "
                    "WHERE approval_id = ? AND status = 'prepared'",
                    (submitted_at, approval_id),
                )
                if updated.rowcount != 1:
                    raise ValueError("approval state changed before reservation")
                if approval["kind"] == "entry":
                    updated = self._connection.execute(
                        "UPDATE decisions SET status = 'submitted' "
                        "WHERE decision_id = ? AND status = 'approval_ready'",
                        (decision["decision_id"],),
                    )
                    if updated.rowcount != 1:
                        raise ValueError("decision state changed before reservation")
                order = self._connection.execute(
                    "SELECT * FROM orders WHERE order_id = ?", (order_id,)
                ).fetchone()
                self.record_audit(
                    "order.reserved",
                    order_id,
                    {"approval_id": approval_id, "client_order_id": client_order_id},
                )
                submission = {
                    "approval": self.get_approval(approval_id),
                    "order": dict(order),
                    "replayed": False,
                }
        if expired:
            raise ValueError("approval has expired")
        assert submission is not None
        return submission

    def orders(self, *, mode: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if mode is None:
                rows = self._connection.execute(
                    "SELECT orders.*, decisions.mode AS mode FROM orders "
                    "JOIN decisions USING(decision_id) ORDER BY submitted_at DESC"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT orders.*, decisions.mode AS mode FROM orders "
                    "JOIN decisions USING(decision_id) WHERE decisions.mode = ? "
                    "ORDER BY submitted_at DESC",
                    (mode,),
                ).fetchall()
            return [dict(row) for row in rows]

    def order_for_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM orders WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            return None if row is None else dict(row)

    def update_order(
        self,
        order_id: str,
        *,
        status: str,
        filled_qty: str | None = None,
        filled_avg_price: str | None = None,
        filled_at: str | None = None,
        filled_debit: str | None = None,
        safe_reference: str | None = None,
    ) -> dict[str, Any]:
        normalized_status = status.strip().lower()
        if not normalized_status:
            raise ValueError("order status cannot be empty")
        with self._transaction():
            existing = self._connection.execute(
                "SELECT decision_id, approval_id FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if existing is None:
                raise KeyError("order not found")
            self._connection.execute(
                """
                UPDATE orders
                SET status = ?, filled_qty = COALESCE(?, filled_qty),
                    filled_avg_price = COALESCE(?, filled_avg_price),
                    filled_at = COALESCE(?, filled_at), updated_at = ?,
                    filled_debit = COALESCE(?, filled_debit),
                    safe_reference = COALESCE(?, safe_reference)
                WHERE order_id = ?
                """,
                (
                    normalized_status,
                    filled_qty,
                    filled_avg_price,
                    filled_at,
                    now_iso(),
                    filled_debit,
                    safe_reference,
                    order_id,
                ),
            )
            self._connection.execute(
                "UPDATE approvals SET status = ? WHERE approval_id = ?",
                (normalized_status, existing["approval_id"]),
            )
            approval = self.get_approval(existing["approval_id"])
            if approval is not None and approval["kind"] == "entry":
                self._connection.execute(
                    "UPDATE decisions SET status = ? WHERE decision_id = ?",
                    (normalized_status, existing["decision_id"]),
                )
            self.record_audit(
                "order.status_changed",
                order_id,
                {"status": normalized_status},
            )
            row = self._connection.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
            return dict(row)

    def reconcile_order_update(
        self,
        order_id: str,
        *,
        status: str,
        filled_qty: str,
        filled_avg_price: str | None,
        filled_at: str | None,
    ) -> dict[str, Any]:
        """Atomically persist broker order state and account for newly filled quantity."""

        normalized_status = status.strip().lower()
        try:
            cumulative_qty = Decimal(filled_qty)
            average_price = None if filled_avg_price is None else Decimal(filled_avg_price)
        except InvalidOperation as error:
            raise ValueError("broker fill fields are not valid decimal values") from error
        if not normalized_status or cumulative_qty < 0:
            raise ValueError("broker order status or fill quantity is invalid")

        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
            if row is None:
                raise KeyError("order not found")
            approval = self.get_approval(row["approval_id"])
            if approval is None:
                raise ValueError("order approval is missing")
            decision = self.get_decision(row["decision_id"])
            if decision is None:
                raise ValueError("order decision is missing")
            accounted_qty = Decimal(row["accounted_filled_qty"] or "0")
            if cumulative_qty < accounted_qty:
                raise ValueError("broker cumulative fill quantity moved backwards")
            if cumulative_qty > 0 and average_price is None:
                raise ValueError("broker reports filled quantity without an average fill price")

            self._connection.execute(
                """
                UPDATE orders SET status = ?, filled_qty = ?, filled_avg_price = ?,
                    filled_at = COALESCE(?, filled_at), updated_at = ?
                WHERE order_id = ?
                """,
                (
                    normalized_status,
                    str(cumulative_qty),
                    None if average_price is None else str(average_price),
                    filled_at,
                    now_iso(),
                    order_id,
                ),
            )

            delta_qty = cumulative_qty - accounted_qty
            if delta_qty > 0 and average_price is not None:
                if approval["kind"] == "entry":
                    self._upsert_filled_entry_position(
                        decision=decision,
                        order=row,
                        quantity=cumulative_qty,
                        average_price=average_price,
                    )
                elif approval["kind"] == "exit":
                    self._apply_filled_exit(
                        position_id=approval["position_id"],
                        delta_quantity=delta_qty,
                        average_price=average_price,
                    )
            self._connection.execute(
                "UPDATE orders SET accounted_filled_qty = ? WHERE order_id = ?",
                (str(cumulative_qty), order_id),
            )
            self._connection.execute(
                "UPDATE approvals SET status = ? WHERE approval_id = ?",
                (normalized_status, row["approval_id"]),
            )
            if approval["kind"] == "entry":
                self._connection.execute(
                    "UPDATE decisions SET status = ? WHERE decision_id = ?",
                    (normalized_status, row["decision_id"]),
                )
            self.record_audit(
                "order.reconciled",
                order_id,
                {
                    "status": normalized_status,
                    "filled_qty": str(cumulative_qty),
                    "newly_accounted_qty": str(delta_qty),
                },
            )
            result = self._connection.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
            return dict(result)

    def _upsert_filled_entry_position(
        self,
        *,
        decision: dict[str, Any],
        order: sqlite3.Row,
        quantity: Decimal,
        average_price: Decimal,
    ) -> None:
        cost_basis = abs(average_price) * Decimal("100") * quantity
        existing = self._connection.execute(
            "SELECT * FROM positions WHERE order_id = ?", (order["order_id"],)
        ).fetchone()
        if existing is None:
            self.create_position(
                decision_id=decision["decision_id"],
                order_id=order["order_id"],
                symbol=decision["symbol"],
                direction=decision["payload"].get("intent", {}).get("direction", "unknown"),
                quantity=str(quantity),
                cost_basis=str(cost_basis),
            )
            return
        self._connection.execute(
            """UPDATE positions SET quantity = ?, cost_basis = ?,
                position_value = ?, unrealized_pnl = '0', status = 'open', updated_at = ?
                WHERE position_id = ?""",
            (
                str(quantity),
                str(cost_basis),
                str(cost_basis),
                now_iso(),
                existing["position_id"],
            ),
        )

    def _apply_filled_exit(
        self,
        *,
        position_id: str | None,
        delta_quantity: Decimal,
        average_price: Decimal,
    ) -> None:
        if position_id is None:
            raise ValueError("exit approval has no linked position")
        position = self._connection.execute(
            "SELECT * FROM positions WHERE position_id = ?", (position_id,)
        ).fetchone()
        if position is None:
            raise ValueError("exit position is missing")
        previous_quantity = Decimal(position["quantity"])
        if delta_quantity > previous_quantity:
            raise ValueError("exit fill exceeds the reconciled open quantity")
        unit_cost = Decimal(position["cost_basis"]) / previous_quantity
        remaining_quantity = previous_quantity - delta_quantity
        exit_credit = abs(average_price) * Decimal("100") * delta_quantity
        realized = Decimal(position["realized_pnl"]) + exit_credit - unit_cost * delta_quantity
        old_value = Decimal(position["position_value"])
        new_value = old_value * remaining_quantity / previous_quantity
        new_cost = unit_cost * remaining_quantity
        status = "closed" if remaining_quantity == 0 else "open"
        self._connection.execute(
            """UPDATE positions SET status = ?, quantity = ?, cost_basis = ?,
                position_value = ?, unrealized_pnl = ?, realized_pnl = ?, updated_at = ?
                WHERE position_id = ?""",
            (
                status,
                str(remaining_quantity),
                str(new_cost),
                str(new_value),
                str(new_value - new_cost),
                str(realized),
                now_iso(),
                position_id,
            ),
        )

    def create_position(
        self,
        *,
        decision_id: str,
        order_id: str,
        symbol: str,
        direction: str,
        cost_basis: str,
        quantity: str = "1",
        mark_at: str | None = None,
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
                    quantity, cost_basis, position_value, unrealized_pnl, realized_pnl,
                    mark_at, updated_at
                ) VALUES(?, ?, ?, ?, 'open', ?, ?, ?, ?, '0', '0', ?, ?)
                """,
                (
                    position_id,
                    decision_id,
                    order_id,
                    symbol,
                    direction,
                    quantity,
                    cost_basis,
                    cost_basis,
                    mark_at,
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
        mark_at: str | None = None,
        reconciliation_status: str | None = None,
        reconciliation_reason: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._connection.execute(
                """
                UPDATE positions
                SET status = ?, position_value = ?, unrealized_pnl = ?,
                    realized_pnl = ?, mark_at = COALESCE(?, mark_at),
                    reconciliation_status = COALESCE(?, reconciliation_status),
                    reconciliation_reason = COALESCE(?, reconciliation_reason),
                    updated_at = ?
                WHERE position_id = ?
                """,
                (
                    status,
                    position_value,
                    unrealized_pnl,
                    realized_pnl,
                    mark_at,
                    reconciliation_status,
                    reconciliation_reason,
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

    def set_position_reconciliation(
        self, position_id: str, *, state: str, reason: str = ""
    ) -> dict[str, Any]:
        if state not in {"matched", "unverified", "discrepancy", "stale_quote"}:
            raise ValueError("unsupported position reconciliation state")
        with self._transaction():
            updated = self._connection.execute(
                "UPDATE positions SET reconciliation_status = ?, "
                "reconciliation_reason = ?, updated_at = ? WHERE position_id = ?",
                (state, reason[:240], now_iso(), position_id),
            )
            if updated.rowcount != 1:
                raise KeyError("position not found")
            result = self._connection.execute(
                "SELECT * FROM positions WHERE position_id = ?", (position_id,)
            ).fetchone()
            return dict(result)

    def positions(self, *, mode: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if mode is None:
                rows = self._connection.execute(
                    "SELECT positions.*, decisions.mode AS mode FROM positions "
                    "JOIN decisions USING(decision_id) ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT positions.*, decisions.mode AS mode FROM positions "
                    "JOIN decisions USING(decision_id) WHERE decisions.mode = ? "
                    "ORDER BY updated_at DESC",
                    (mode,),
                ).fetchall()
            return [dict(row) for row in rows]

    def risk_exposure(self, *, mode: str) -> PortfolioRiskExposure:
        """Reconstruct defined-risk exposure from reconciled local spread state."""

        terminal = TERMINAL_ORDER_STATUSES
        active_statuses = {
            "submitting",
            "unknown",
            "submitted",
            "accepted",
            "new",
            "pending_new",
            "partially_filled",
            "held",
        }
        with self._lock:
            positions = [item for item in self.positions(mode=mode) if item["status"] == "open"]
            open_risk = Decimal("0")
            for position in positions:
                if position["reconciliation_status"] not in {"matched", "stale_quote"}:
                    raise ValueError("open option exposure is not reconciled")
                quantity = Decimal(position["quantity"])
                cost_basis = Decimal(position["cost_basis"])
                if quantity <= 0 or cost_basis <= 0:
                    raise ValueError("open option exposure has invalid risk fields")
                # A long debit vertical's maximum loss is the actual entry debit.
                open_risk += cost_basis

            pending_risk = Decimal("0")
            pending_orders = 0
            for order in self.orders(mode=mode):
                order_status = str(order["status"]).lower()
                if order_status in terminal:
                    continue
                if order_status not in active_statuses:
                    raise ValueError("local order has an unknown reconciliation state")
                approval = self.get_approval(order["approval_id"])
                if approval is None:
                    raise ValueError("pending order approval is unavailable")
                if approval["kind"] != "entry":
                    continue
                approved_quantity = Decimal(str(approval["quantity"]))
                remaining_quantity = approved_quantity - Decimal(str(order["filled_qty"] or "0"))
                if approved_quantity <= 0 or remaining_quantity < 0:
                    raise ValueError("pending order quantity is inconsistent")
                if remaining_quantity == 0:
                    continue
                approved_risk = Decimal(str(approval["maximum_loss"]))
                if approved_risk <= 0:
                    raise ValueError("pending order risk is unavailable")
                pending_orders += 1
                pending_risk += approved_risk * remaining_quantity / approved_quantity

            switch = self.kill_switch()
            return PortfolioRiskExposure(
                open_options_risk=open_risk + pending_risk,
                open_option_positions=len(positions),
                pending_option_orders=pending_orders,
                kill_switch_enabled=bool(switch["enabled"]),
            )

    def daily_equity_baseline(
        self,
        *,
        trading_day: str,
        broker_last_equity: Decimal | None,
    ) -> Decimal | None:
        """Persist the broker's prior-close equity for restart-safe daily P&L."""

        day = date.fromisoformat(trading_day).isoformat()
        if broker_last_equity is not None and broker_last_equity <= 0:
            raise ValueError("broker equity baseline must be positive")
        with self._transaction():
            row = self._connection.execute(
                "SELECT trading_day, broker_last_equity FROM daily_equity_baseline "
                "WHERE singleton = 1"
            ).fetchone()
            baseline = None if row is None else Decimal(row["broker_last_equity"])
            if broker_last_equity is not None and (
                row is None or row["trading_day"] != day or baseline != broker_last_equity
            ):
                self._connection.execute(
                    "INSERT INTO daily_equity_baseline(singleton, trading_day, "
                    "broker_last_equity, updated_at) VALUES(1, ?, ?, ?) "
                    "ON CONFLICT(singleton) DO UPDATE SET trading_day = excluded.trading_day, "
                    "broker_last_equity = excluded.broker_last_equity, "
                    "updated_at = excluded.updated_at",
                    (day, str(broker_last_equity), now_iso()),
                )
                baseline_hash = hashlib.sha256(str(broker_last_equity).encode()).hexdigest()
                self.record_audit(
                    "risk.daily_equity_baseline",
                    day,
                    {"baseline_sha256": baseline_hash},
                )
                baseline = broker_last_equity
            if row is not None and row["trading_day"] != day and broker_last_equity is None:
                return None
            return baseline

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
        entry_id = f"journal_{uuid.uuid4().hex[:20]}"
        timestamp = now_iso()
        with self._transaction():
            if decision_id is not None and self.get_decision(decision_id) is None:
                raise ValueError("journal decision reference not found")
            self._connection.execute(
                "INSERT INTO journal_entries("
                "entry_id, decision_id, body, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (entry_id, decision_id, clean, timestamp, timestamp),
            )
            self.record_audit("journal.created", entry_id, {"decision_id": decision_id})
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
        with self._transaction():
            self._connection.execute(
                "UPDATE kill_switch SET enabled = ?, reason = ?, updated_at = ? "
                "WHERE singleton = 1",
                (int(enabled), reason.strip(), now_iso()),
            )
            result = self.kill_switch()
            self.record_audit("kill_switch.changed", "kill_switch", result)
            return result

    def record_audit(self, event_type: str, entity_id: str, payload: dict[str, Any]) -> None:
        """Append a sanitized, hash-linked local audit event."""

        occurred_at = now_iso()
        with self._transaction():
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
