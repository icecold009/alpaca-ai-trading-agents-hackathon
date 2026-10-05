"""Verify, back up, and restore the local RiskCourt SQLite state database."""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from riskcourt.personal_store import SCHEMA_VERSION

BACKUP_NAME = re.compile(r"^riskcourt-\d{8}T\d{6}Z\.sqlite3$")


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri_path = quote(path.resolve().as_posix(), safe="/:")
    return sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)


def verify_database(path: Path) -> int:
    """Require a readable SQLite file with a clean integrity check and current schema."""

    if not path.is_file():
        raise FileNotFoundError("database file does not exist")
    with closing(_readonly_connection(path)) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if result is None or result[0] != "ok":
        raise ValueError("database integrity check failed")
    if version != SCHEMA_VERSION:
        raise ValueError("database schema version is not supported")
    return version


def _copy_database(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def backup_database(source: Path, destination: Path) -> Path:
    """Create a verified point-in-time backup without replacing an existing file."""

    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("backup destination must differ from the database")
    if destination.exists():
        raise FileExistsError("backup destination already exists")
    if not source.is_file():
        raise FileNotFoundError("database file does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        _copy_database(source, staging)
        verify_database(staging)
        if os.name != "nt":
            staging.chmod(0o600)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def restore_database(backup: Path, destination: Path, *, overwrite: bool = False) -> Path:
    """Restore a verified backup, retaining a verified rollback copy when replacing."""

    backup = backup.resolve()
    destination = destination.resolve()
    if backup == destination:
        raise ValueError("restore source must differ from the database")
    verify_database(backup)
    if destination.exists() and not overwrite:
        raise FileExistsError("database exists; pass --overwrite to replace it")
    for suffix in ("-wal", "-shm"):
        if Path(f"{destination}{suffix}").exists():
            raise RuntimeError("database sidecar files exist; stop the local server first")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.{uuid4().hex}.restore")
    try:
        _copy_database(backup, staging)
        verify_database(staging)
        if destination.exists():
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            rollback = destination.with_name(
                f"{destination.name}.pre-restore-{timestamp}.sqlite3"
            )
            backup_database(destination, rollback)
        if os.name != "nt":
            staging.chmod(0o600)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def prune_backups(directory: Path, *, keep: int, apply: bool = False) -> list[Path]:
    """List or remove old managed backups, keeping at least the newest requested count."""

    if not 1 <= keep <= 1000:
        raise ValueError("backup retention must keep between 1 and 1000 files")
    if not directory.is_dir():
        raise FileNotFoundError("backup directory does not exist")
    backups = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and BACKUP_NAME.fullmatch(path.name)
        ),
        key=lambda path: path.name,
    )
    removable = backups[:-keep]
    if apply:
        for path in removable:
            path.unlink()
    return removable


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="check SQLite integrity and schema")
    verify.add_argument("--database", type=Path, required=True)
    backup = commands.add_parser("backup", help="create a verified backup")
    backup.add_argument("--database", type=Path, required=True)
    backup.add_argument("--destination", type=Path, required=True)
    restore = commands.add_parser("restore", help="restore a verified backup")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--database", type=Path, required=True)
    restore.add_argument("--overwrite", action="store_true")
    prune = commands.add_parser("prune", help="preview or remove old managed backups")
    prune.add_argument("--directory", type=Path, required=True)
    prune.add_argument("--keep", type=int, required=True)
    prune.add_argument("--apply", action="store_true", help="delete the listed old backups")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "verify":
        version = verify_database(args.database)
        print(f"Database integrity is ok; schema version {version}.")
    elif args.command == "backup":
        path = backup_database(args.database, args.destination)
        print(f"Verified backup created at {path}.")
    elif args.command == "restore":
        path = restore_database(args.backup, args.database, overwrite=args.overwrite)
        print(f"Verified backup restored to {path}.")
    else:
        removable = prune_backups(args.directory, keep=args.keep, apply=args.apply)
        action = "Removed" if args.apply else "Would remove"
        print(f"{action} {len(removable)} managed backup(s).")
        for path in removable:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
