from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from scripts.resolve_forecast_outcomes import parse_evidence_csv

from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.personal_store import SCHEMA_VERSION, PersonalStore

PRODUCED_AT = datetime(2026, 10, 1, 19, 55, tzinfo=UTC)
HORIZON_AT = datetime(2026, 10, 1, 20, 0, tzinfo=UTC)


def make_decision(
    store: PersonalStore, *, produced_at: datetime = PRODUCED_AT
) -> str:
    case = RecordedCaseRepository().get("case_edge_positive")
    assert case is not None
    payload = case.model_dump(mode="json")
    payload.update(
        {
            "as_of": produced_at.isoformat(),
            "underlying_symbol": "SPY",
            "provider": {"mode": "typesafe", "simulated": False},
            "forecast_event": {
                "symbol": "SPY",
                "threshold": "100",
                "condition": "underlying_price_above_threshold",
                "horizon_at": HORIZON_AT.isoformat(),
                "settlement_rule": (
                    "last regular-session underlying quote at the broker calendar close"
                ),
                "calendar_source": "Alpaca trading calendar",
                "role_mode": "two-role-no-news",
                "minimum_quorum": 2,
            },
            "forecasts": [
                {
                    "forecast_id": "forecast_market",
                    "case_id": str(payload["case_id"]),
                    "juror_id": "juror_market",
                    "outcome": "above_strike",
                    "probability": "0.65",
                    "calibration_score": "0.80",
                    "confidence_stake": "0.70",
                    "produced_at": produced_at.isoformat(),
                    "horizon_at": HORIZON_AT.isoformat(),
                    "evidence_ids": ["quote_1", "bar_1"],
                    "model_version": "test-model-v1",
                    "prompt_version": "test-prompt-v1",
                    "provider_metadata": {
                        "evidence_quality": "0.75",
                        "calibration_basis": "configured_shrinkage_prior_v1",
                    },
                },
                {
                    "forecast_id": "forecast_volatility",
                    "case_id": str(payload["case_id"]),
                    "juror_id": "juror_volatility",
                    "outcome": "above_strike",
                    "probability": "0.60",
                    "calibration_score": "0.80",
                    "confidence_stake": "0.65",
                    "produced_at": produced_at.isoformat(),
                    "horizon_at": HORIZON_AT.isoformat(),
                    "evidence_ids": ["option_1"],
                    "model_version": "test-model-v1",
                    "prompt_version": "test-prompt-v1",
                    "provider_metadata": {
                        "evidence_quality": "0.70",
                        "calibration_basis": "configured_shrinkage_prior_v1",
                    },
                },
            ],
        }
    )
    scan_id = store.create_scan("recorded", ["SPY"])
    return store.save_decision(scan_id=scan_id, mode="recorded", payload=payload)


def resolution_row(
    decision_id: str,
    *,
    observed_at: datetime | None = None,
    price: str = "101.25",
) -> dict[str, str]:
    return {
        "decision_id": decision_id,
        "observed_at": (observed_at or HORIZON_AT - timedelta(seconds=30)).isoformat(),
        "settlement_price": price,
        "source_name": "alpaca_sip",
        "source_reference": "spy-official-bar-20261001T2000Z",
    }


def resolve(store: PersonalStore, row: dict[str, str], *, at: datetime | None = None) -> list[
    dict[str, object]
]:
    evidence = json.dumps(row, sort_keys=True).encode("utf-8")
    return store.resolve_forecast_outcomes(
        [row],
        evidence_filename="settlement-evidence.json",
        evidence_bytes=evidence,
        resolved_at=at or HORIZON_AT + timedelta(seconds=5),
    )


def test_forecasts_resolve_from_immutable_hashed_evidence(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    decision_id = make_decision(store)
    pending = store.pending_forecast_events()
    assert len(pending) == 1
    assert pending[0]["decision_id"] == decision_id
    assert pending[0]["forecast_count"] == 2

    outcomes = resolve(store, resolution_row(decision_id))
    assert len(outcomes) == 1
    assert outcomes[0]["realized"] is True
    digest = str(outcomes[0]["evidence_sha256"])
    assert len(digest) == 64
    saved_evidence = store._connection.execute(
        "SELECT content FROM outcome_evidence WHERE sha256 = ?", (digest,)
    ).fetchone()
    assert saved_evidence is not None
    assert hashlib.sha256(bytes(saved_evidence["content"])).hexdigest() == digest

    samples = store.resolved_forecast_samples()
    assert len(samples) == 2
    assert {row["juror_id"] for row in samples} == {"juror_market", "juror_volatility"}
    assert {row["realized"] for row in samples} == {1}
    assert {row["provider_quality"] for row in samples} == {"0.75", "0.70"}
    assert {row["evidence_count"] for row in samples} == {1, 2}
    assert {row["calibration_version"] for row in samples} == {
        "configured_shrinkage_prior_v1"
    }
    assert store.pending_forecast_events() == []

    with pytest.raises(ValueError, match="immutable"):
        resolve(store, resolution_row(decision_id, price="90"))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store._connection.execute(
            "UPDATE forecast_outcomes SET realized = 0 WHERE decision_id = ?",
            (decision_id,),
        )
    store.close()


@pytest.mark.parametrize(
    ("row_kwargs", "resolved_at", "message"),
    [
        ({}, HORIZON_AT - timedelta(seconds=1), "horizon has not elapsed"),
        (
            {"observed_at": HORIZON_AT + timedelta(seconds=1)},
            HORIZON_AT + timedelta(seconds=5),
            "within five minutes",
        ),
        (
            {"observed_at": HORIZON_AT - timedelta(minutes=6)},
            HORIZON_AT + timedelta(seconds=5),
            "within five minutes",
        ),
    ],
)
def test_outcome_resolution_rejects_lookahead_and_bad_timing(
    tmp_path: Path,
    row_kwargs: dict[str, object],
    resolved_at: datetime,
    message: str,
) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    decision_id = make_decision(store)
    row = resolution_row(decision_id, **row_kwargs)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=message):
        resolve(store, row, at=resolved_at)
    assert store.resolved_forecast_samples(include_simulated=True) == []
    assert store._connection.execute("SELECT COUNT(*) FROM outcome_evidence").fetchone()[0] == 0
    store.close()


def test_settlement_observation_must_follow_every_forecast(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    decision_id = make_decision(
        store,
        produced_at=HORIZON_AT - timedelta(minutes=3),
    )
    row = resolution_row(
        decision_id,
        observed_at=HORIZON_AT - timedelta(minutes=4),
    )

    with pytest.raises(ValueError, match="follow every forecast"):
        resolve(store, row)
    assert store.resolved_forecast_samples(include_simulated=True) == []
    store.close()


def test_outcome_import_is_atomic_and_rejects_unknown_duplicate_or_invalid_source(
    tmp_path: Path,
) -> None:
    store = PersonalStore(tmp_path / "riskcourt.sqlite3")
    decision_id = make_decision(store)
    evidence = b"operator supplied evidence"
    valid = resolution_row(decision_id)
    unknown = resolution_row("decision_missing")
    with pytest.raises(KeyError, match="no persisted forecast"):
        store.resolve_forecast_outcomes(
            [valid, unknown],
            evidence_filename="outcomes.csv",
            evidence_bytes=evidence,
            resolved_at=HORIZON_AT + timedelta(seconds=5),
        )
    assert store._connection.execute("SELECT COUNT(*) FROM forecast_outcomes").fetchone()[0] == 0
    assert store._connection.execute("SELECT COUNT(*) FROM outcome_evidence").fetchone()[0] == 0

    invalid_source = {**valid, "source_reference": "https://example.test/?token=secret"}
    with pytest.raises(ValueError, match="sanitized opaque ID"):
        resolve(store, invalid_source)
    with pytest.raises(ValueError, match="positive finite"):
        resolve(store, resolution_row(decision_id, price="NaN"))
    assert store.resolved_forecast_samples(include_simulated=True) == []
    store.close()


def test_schema_ten_upgrade_rolls_back_all_ddl_on_failure(tmp_path: Path) -> None:
    database = tmp_path / "riskcourt.sqlite3"
    initial = PersonalStore(database)
    assert initial.health_check() == {"ok": True, "schema_version": SCHEMA_VERSION}
    initial.close()

    connection = sqlite3.connect(database)
    for trigger in (
        "forecast_observations_no_update",
        "forecast_observations_no_delete",
        "forecast_outcomes_no_update",
        "forecast_outcomes_no_delete",
        "outcome_evidence_no_update",
        "outcome_evidence_no_delete",
    ):
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    for table in ("forecast_outcomes", "outcome_evidence", "forecast_observations"):
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    connection.execute("CREATE TABLE forecast_outcomes (invalid_column TEXT)")
    connection.execute("PRAGMA user_version = 9")
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.OperationalError):
        PersonalStore(database)

    check = sqlite3.connect(database)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 9
    assert check.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'forecast_observations'"
    ).fetchone() is None
    check.close()


def test_outcome_csv_schema_is_strict_and_deduplicated() -> None:
    valid = (
        b"decision_id,observed_at,settlement_price,source_name,source_reference\n"
        b"decision_1,2026-10-01T19:59:30+00:00,101.25,alpaca_sip,spy-close-20261001\n"
    )
    assert parse_evidence_csv(valid)[0]["settlement_price"] == "101.25"
    with pytest.raises(ValueError, match="header"):
        parse_evidence_csv(b"decision_id,settlement_price\n")
    duplicated = valid + valid.splitlines(keepends=True)[1]
    with pytest.raises(ValueError, match="unique"):
        parse_evidence_csv(duplicated)
