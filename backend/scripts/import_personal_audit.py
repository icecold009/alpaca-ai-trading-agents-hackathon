"""Import validated legacy JSON event logs into the personal SQLite audit history."""

from __future__ import annotations

import argparse
from pathlib import Path

from riskcourt.personal_store import PersonalStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-dir", type=Path, default=Path(".riskcourt") / "events")
    parser.add_argument("--state-dir", type=Path, default=Path(".riskcourt"))
    args = parser.parse_args()

    store = PersonalStore(args.state_dir / "riskcourt.sqlite3")
    imported = sum(
        store.import_legacy_event_log(path) for path in sorted(args.events_dir.glob("*.json"))
    )
    print(f"Imported {imported} legacy audit events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
