from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from scripts.manage_personal_state import (
    backup_database,
    prune_backups,
    restore_database,
    verify_database,
)

from riskcourt.personal_store import SCHEMA_VERSION, PersonalStore


def test_schema_migration_rolls_back_all_changes_on_failure(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 8")

    with pytest.raises(sqlite3.OperationalError):
        PersonalStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
        table_names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "daily_equity_baseline" not in table_names


def test_backup_verify_and_restore_keep_a_rollback_copy(tmp_path: Path) -> None:
    database = tmp_path / "riskcourt.sqlite3"
    store = PersonalStore(database)
    store.set_kill_switch(True, "saved in verified backup")
    store.close()

    backup = backup_database(database, tmp_path / "private" / "riskcourt-backup.sqlite3")
    assert verify_database(backup) == SCHEMA_VERSION
    with pytest.raises(FileExistsError, match="already exists"):
        backup_database(database, backup)

    store = PersonalStore(database)
    store.set_kill_switch(False, "current state before restore")
    store.close()
    with pytest.raises(FileExistsError, match="--overwrite"):
        restore_database(backup, database)

    restored = restore_database(backup, database, overwrite=True)
    assert restored == database.resolve()
    assert len(list(tmp_path.glob("riskcourt.sqlite3.pre-restore-*.sqlite3"))) == 1

    store = PersonalStore(database)
    assert store.kill_switch()["enabled"] is True
    assert store.kill_switch()["reason"] == "saved in verified backup"
    store.close()


def test_restore_rejects_unverified_or_active_database_sidecars(tmp_path: Path) -> None:
    database = tmp_path / "riskcourt.sqlite3"
    PersonalStore(database).close()
    backup = backup_database(database, tmp_path / "backup.sqlite3")
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_bytes(b"not a database")
    with pytest.raises(sqlite3.DatabaseError):
        verify_database(invalid)

    sidecar = Path(f"{database}-wal")
    sidecar.touch()
    with pytest.raises(RuntimeError, match="stop the local server"):
        restore_database(backup, database, overwrite=True)


def test_backup_pruning_is_scoped_and_requires_explicit_apply(tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    directory.mkdir()
    managed = [directory / f"riskcourt-2026100{day}T120000Z.sqlite3" for day in (1, 2, 3)]
    for path in managed:
        path.touch()
    unrelated = directory / "riskcourt-other.sqlite3"
    unrelated.touch()

    preview = prune_backups(directory, keep=2)
    assert preview == managed[:1]
    assert managed[0].exists()
    assert unrelated.exists()

    removed = prune_backups(directory, keep=2, apply=True)
    assert removed == managed[:1]
    assert not managed[0].exists()
    assert all(path.exists() for path in managed[1:])
    assert unrelated.exists()
