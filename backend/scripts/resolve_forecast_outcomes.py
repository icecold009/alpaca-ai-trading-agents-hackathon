"""Import immutable forecast settlement evidence or print calibration reports."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from riskcourt.personal_store import MAX_OUTCOME_EVIDENCE_BYTES, PersonalStore
from riskcourt.typesafe_calibration import (
    ForecastCalibrationSample,
    build_forecast_calibration_report,
)

CSV_FIELDS = (
    "decision_id",
    "observed_at",
    "settlement_price",
    "source_name",
    "source_reference",
)


def parse_evidence_csv(content: bytes) -> list[dict[str, str]]:
    """Parse the deliberately small, allowlisted outcome evidence format."""

    if not content or len(content) > MAX_OUTCOME_EVIDENCE_BYTES:
        raise ValueError("outcome evidence file must contain 1 to 1,000,000 bytes")
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("outcome evidence must be UTF-8 CSV") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != CSV_FIELDS:
        raise ValueError("outcome CSV header must match the documented field order")
    rows: list[dict[str, str]] = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("outcome CSV row has missing or unexpected columns")
        normalized = {key: str(row[key]).strip() for key in CSV_FIELDS}
        if any(not value for value in normalized.values()):
            raise ValueError("outcome CSV values must not be empty")
        rows.append(normalized)
        if len(rows) > 1000:
            raise ValueError("outcome import cannot exceed 1000 rows")
    if not rows:
        raise ValueError("outcome CSV must contain at least one row")
    if len({row["decision_id"] for row in rows}) != len(rows):
        raise ValueError("outcome CSV decision IDs must be unique")
    return rows


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve", help="import later settlement evidence from CSV")
    resolve.add_argument("--database", type=Path, required=True)
    resolve.add_argument("--input", type=Path, required=True)
    pending = commands.add_parser("pending", help="list unresolved forecast event contracts")
    pending.add_argument("--database", type=Path, required=True)
    report = commands.add_parser("report", help="print chronological forecast evaluation")
    report.add_argument("--database", type=Path, required=True)
    report.add_argument("--mode", choices=("recorded", "paper"))
    report.add_argument(
        "--include-simulated",
        action="store_true",
        help="include deterministic test/stub forecasts in separate groups",
    )
    return parser


def _samples(store: PersonalStore, *, include_simulated: bool, mode: str | None) -> list[
    ForecastCalibrationSample
]:
    return [
        ForecastCalibrationSample(
            decision_id=str(row["decision_id"]),
            forecast_id=str(row["forecast_id"]),
            mode=str(row["mode"]),
            provider_mode=str(row["provider_mode"]),
            juror_id=str(row["juror_id"]),
            model_version=str(row["model_version"]),
            prompt_version=str(row["prompt_version"]),
            calibration_version=str(row["calibration_version"]),
            probability=Decimal(str(row["probability"])),
            calibration_score=Decimal(str(row["calibration_score"])),
            realized=bool(row["realized"]),
            produced_at=datetime.fromisoformat(str(row["produced_at"])),
            horizon_at=datetime.fromisoformat(str(row["horizon_at"])),
            resolved_at=datetime.fromisoformat(str(row["resolved_at"])),
            simulated=bool(row["simulated"]),
        )
        for row in store.resolved_forecast_samples(
            include_simulated=include_simulated, mode=mode
        )
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.database.is_file():
        print("forecast database does not exist", file=sys.stderr)
        return 2
    store = PersonalStore(args.database)
    try:
        if args.command == "resolve":
            content = args.input.read_bytes()
            rows = parse_evidence_csv(content)
            results = store.resolve_forecast_outcomes(
                rows,
                evidence_filename=args.input.name,
                evidence_bytes=content,
            )
            print(
                json.dumps(
                    {
                        "resolved_count": len(results),
                        "outcomes": results,
                        "evidence_sha256": results[0]["evidence_sha256"],
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "pending":
            print(
                json.dumps(
                    _json_value(store.pending_forecast_events()), indent=2, sort_keys=True
                )
            )
            return 0

        groups = build_forecast_calibration_report(
            _samples(
                store,
                include_simulated=args.include_simulated,
                mode=args.mode,
            ),
            include_simulated=args.include_simulated,
        )
        print(json.dumps(_json_value(groups), indent=2, sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError) as error:
        print(f"forecast evaluation failed: {error}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
