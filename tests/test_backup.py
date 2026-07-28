import sqlite3
from datetime import datetime

import pytest

from app.backup import apply_retention, create_backup, integrity_check, restore_backup


def make_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute("create table sample (value text)")
        connection.execute("insert into sample values ('preserved')")


def test_backup_restore_and_integrity_use_separate_paths(tmp_path):
    live, backups, restored = tmp_path / "live.db", tmp_path / "backups", tmp_path / "restored.test.db"
    make_database(live)
    backup = create_backup(live, backups, now=datetime(2026, 7, 28, 14, 30, 15))
    restore_backup(backup, restored)
    assert backup.name == "joshs_corner_2026-07-28_143015.db"
    assert integrity_check(backup) and integrity_check(restored)
    with sqlite3.connect(restored) as connection: assert connection.execute("select value from sample").fetchone()[0] == "preserved"
    with sqlite3.connect(live) as connection: assert connection.execute("select value from sample").fetchone()[0] == "preserved"


def test_backup_names_are_unique_and_secondary_failure_keeps_local_copy(tmp_path):
    live, backups = tmp_path / "live.db", tmp_path / "backups"; make_database(live)
    first = create_backup(live, backups, now=datetime(2026, 7, 28, 14, 30, 15))
    second = create_backup(live, backups, now=datetime(2026, 7, 28, 14, 30, 15), secondary_dir=tmp_path / "file")
    assert first != second and first.exists() and second.exists()


def test_invalid_backup_and_live_replacement_require_explicit_force(tmp_path):
    live, invalid = tmp_path / "live.db", tmp_path / "invalid.db"; make_database(live); invalid.write_text("not sqlite")
    with pytest.raises(ValueError): restore_backup(invalid, tmp_path / "target.test.db")
    backup = create_backup(live, tmp_path / "backups")
    with pytest.raises(PermissionError): restore_backup(backup, live)


def test_retention_keeps_recent_weekly_and_monthly_representatives(tmp_path):
    for name in ("joshs_corner_2026-07-28_100000.db", "joshs_corner_2026-06-01_100000.db", "joshs_corner_2025-01-01_100000.db"):
        (tmp_path / name).write_bytes(b"x")
    candidates = apply_retention(tmp_path, now=datetime(2026, 7, 28))
    assert (tmp_path / "joshs_corner_2026-07-28_100000.db") not in candidates
