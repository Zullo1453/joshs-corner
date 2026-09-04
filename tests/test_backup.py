import sqlite3
from datetime import datetime
import os

import pytest

from app.backup import (
    MONTHLY_PACKAGE_LIMIT,
    ROLLING_PACKAGE_LIMIT,
    _prune_validated,
    apply_retention,
    create_backup,
    create_backup_package,
    create_rolling_backup_package,
    create_scheduled_backups,
    integrity_check,
    restore_backup,
    validate_backup_package,
)


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


def test_direct_rolling_package_creation_retains_ten_validated_zips_only(tmp_path):
    live, uploads, root = tmp_path / "live.db", tmp_path / "uploads", tmp_path / "backups"
    rolling, historical = root / "rolling", root / "migration-safety"
    make_database(live)
    legacy = create_backup(live, rolling, now=datetime(2026, 1, 1, 8))
    historical_package = create_backup_package(live, uploads, historical, now=datetime(2026, 1, 1, 9))
    created = []
    for day in range(1, 15):
        timestamp = datetime(2026, 2, day, 12)
        package = create_rolling_backup_package(live, uploads, rolling, now=timestamp)
        os.utime(package, (timestamp.timestamp(), timestamp.timestamp()))
        created.append(package)

    retained = sorted(rolling.glob("joshs_corner_backup_*.zip"), key=lambda path: path.stat().st_mtime)
    assert retained == created[-ROLLING_PACKAGE_LIMIT:]
    assert all(validate_backup_package(package) for package in retained)
    assert legacy.exists()
    assert historical_package.exists() and validate_backup_package(historical_package)


def test_failed_direct_rolling_validation_does_not_prune_existing_packages(tmp_path, monkeypatch):
    live, uploads, rolling = tmp_path / "live.db", tmp_path / "uploads", tmp_path / "rolling"
    make_database(live)
    for day in range(1, ROLLING_PACKAGE_LIMIT + 1):
        package = create_rolling_backup_package(live, uploads, rolling, now=datetime(2026, 3, day, 12))
        timestamp = datetime(2026, 3, day, 12)
        os.utime(package, (timestamp.timestamp(), timestamp.timestamp()))
    before = sorted(path.name for path in rolling.glob("*.zip"))

    monkeypatch.setattr("app.backup.validate_backup_package", lambda _package: (_ for _ in ()).throw(ValueError("invalid")))
    with pytest.raises(ValueError):
        create_rolling_backup_package(live, uploads, rolling, now=datetime(2026, 3, 20, 12))

    assert sorted(path.name for path in rolling.glob("*.zip")) == before


def test_scheduled_rolling_retention_and_monthly_retention_are_independent(tmp_path):
    live, uploads, root = tmp_path / "live.db", tmp_path / "uploads", tmp_path / "backups"
    rolling, monthly = root / "rolling", root / "monthly"
    make_database(live)
    rolling_packages = []
    for day in range(1, ROLLING_PACKAGE_LIMIT + 1):
        timestamp = datetime(2026, 1, day, 12)
        package = create_backup_package(live, uploads, rolling, now=timestamp)
        os.utime(package, (timestamp.timestamp(), timestamp.timestamp()))
        rolling_packages.append(package)
    monthly_packages = []
    for month in range(1, MONTHLY_PACKAGE_LIMIT + 1):
        timestamp = datetime(2025, month, 1, 12)
        package = create_backup_package(live, uploads, monthly, now=timestamp)
        os.utime(package, (timestamp.timestamp(), timestamp.timestamp()))
        monthly_packages.append(package)

    rolling_backup, monthly_backup = create_scheduled_backups(
        live, root, now=datetime(2026, 2, 10, 12), uploads_dir=uploads
    )

    assert rolling_backup is not None and rolling_backup.exists()
    assert monthly_backup is not None and monthly_backup.exists()
    assert len(list(rolling.glob("joshs_corner_backup_*.zip"))) == ROLLING_PACKAGE_LIMIT
    assert rolling_packages[0] not in rolling.iterdir()
    assert len(list(monthly.glob("joshs_corner_backup_*.zip"))) == MONTHLY_PACKAGE_LIMIT
    assert monthly_packages[0] not in monthly.iterdir()
    assert validate_backup_package(rolling_backup)
    assert validate_backup_package(monthly_backup)
