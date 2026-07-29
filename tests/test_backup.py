import sqlite3
from datetime import datetime
import os

import pytest

from app.backup import _prune_validated, apply_retention, create_backup, create_backup_package, create_scheduled_backups, integrity_check, restore_backup, validate_backup_package


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
    secondary_file = tmp_path / "secondary-file"; secondary_file.write_text("not a folder")
    second = create_backup(live, backups, now=datetime(2026, 7, 28, 14, 30, 15), secondary_dir=secondary_file)
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


def test_validated_retention_keeps_ten_rolling_backups_and_never_prunes_invalid_files(tmp_path):
    live, rolling = tmp_path / "live.db", tmp_path / "rolling"; make_database(live)
    for day in range(1, 12):
        timestamp = datetime(2026, 6, day, 12)
        backup = create_backup(live, rolling, now=timestamp)
        os.utime(backup, (timestamp.timestamp(), timestamp.timestamp()))
    invalid = rolling / "joshs_corner_unreadable.db"; invalid.write_text("not a database")
    _prune_validated(rolling, 10)
    assert len([path for path in rolling.glob("*.db") if integrity_check(path)]) == 10
    assert invalid.exists()
    _prune_validated(rolling, 0)
    assert len([path for path in rolling.glob("*.db") if integrity_check(path)]) == 1


def test_scheduled_monthly_archive_only_copies_monthly_backup_to_secondary(tmp_path):
    live, root, secondary = tmp_path / "live.db", tmp_path / "backups", tmp_path / "secondary-monthly"
    make_database(live)
    monthly = root / "monthly"
    months = [
        datetime(2025, 7, 1), datetime(2025, 8, 1), datetime(2025, 9, 1),
        datetime(2025, 10, 1), datetime(2025, 11, 1), datetime(2025, 12, 1),
        datetime(2026, 1, 1), datetime(2026, 2, 1), datetime(2026, 3, 1),
        datetime(2026, 4, 1), datetime(2026, 5, 1), datetime(2026, 6, 1),
    ]
    for timestamp in months:
        backup = create_backup(live, monthly, now=timestamp)
        os.utime(backup, (timestamp.timestamp(), timestamp.timestamp()))
    _, archive = create_scheduled_backups(live, root, secondary, now=datetime(2026, 7, 28))
    assert archive is not None and archive.parent == monthly
    assert len([path for path in monthly.glob("*.db") if integrity_check(path)]) == 12
    assert archive.suffix == ".zip"
    assert [path.name for path in secondary.glob("*.zip")] == [archive.name]
    _, repeated_archive = create_scheduled_backups(live, root, secondary, now=datetime(2026, 7, 28))
    assert repeated_archive == archive
    assert len([path for path in monthly.glob("*.db") if integrity_check(path)]) == 12


def test_zip_backup_package_and_separate_restore_include_uploads(tmp_path):
    live, uploads, backups = tmp_path / "live.db", tmp_path / "uploads", tmp_path / "backups"
    make_database(live); uploads.mkdir(); (uploads / "image.webp").write_bytes(b"image bytes")
    package = create_backup_package(live, uploads, backups, now=datetime(2026, 7, 28, 14, 30, 15))
    manifest = validate_backup_package(package)
    target, restored_uploads = tmp_path / "restored.db", tmp_path / "restored_uploads"
    restore_backup(package, target, uploads_target=restored_uploads)
    assert manifest["attachment_count"] == 1 and integrity_check(target)
    assert (restored_uploads / "image.webp").read_bytes() == b"image bytes"
