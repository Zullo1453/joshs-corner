"""SQLite backup, validation, retention, and non-destructive restore helpers."""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import hashlib
import json
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)
ROLLING_PACKAGE_LIMIT = 10
MONTHLY_PACKAGE_LIMIT = 12


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _migration_revision(database: Path) -> str | None:
    try:
        with sqlite3.connect(database) as connection:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.DatabaseError:
        return None


def create_backup_package(source: Path, uploads_dir: Path, backup_dir: Path, now=None) -> Path:
    """Create and validate a ZIP containing a consistent database and local uploads."""
    source, uploads_dir, backup_dir = Path(source), Path(uploads_dir), Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    target = backup_dir / f"joshs_corner_backup_{stamp}.zip"
    suffix = 1
    while target.exists():
        target = backup_dir / f"joshs_corner_backup_{stamp}_{suffix}.zip"; suffix += 1
    temporary = Path(tempfile.mkdtemp(prefix="joshs_corner_backup_"))
    try:
        database_copy = temporary / "joshs_corner.db"
        create_backup(source, temporary, now=now)
        copied = next(temporary.glob("joshs_corner_*.db")); copied.replace(database_copy)
        if not integrity_check(database_copy):
            raise RuntimeError("Backup database integrity check failed")
        files = [{"path": "joshs_corner.db", "sha256": _checksum(database_copy), "size": database_copy.stat().st_size}]
        upload_files = []
        if uploads_dir.is_dir():
            for source_file in sorted(path for path in uploads_dir.rglob("*") if path.is_file()):
                relative = source_file.relative_to(uploads_dir)
                if any(part in {"", ".", ".."} for part in relative.parts):
                    continue
                archive_path = Path("uploads") / relative
                upload_files.append((source_file, archive_path))
                files.append({"path": archive_path.as_posix(), "sha256": _checksum(source_file), "size": source_file.stat().st_size})
        manifest = {
            "format_version": 2,
            "created_at": (now or datetime.now()).isoformat(),
            "database_filename": "joshs_corner.db",
            "database_integrity": "ok",
            "attachment_count": len(upload_files),
            "total_upload_size": sum(item["size"] for item in files[1:]),
            "migration_revision": _migration_revision(database_copy),
            "files": files,
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as package:
            package.write(database_copy, "joshs_corner.db")
            for source_file, archive_path in upload_files:
                package.write(source_file, archive_path.as_posix())
            package.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    try:
        validate_backup_package(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    LOGGER.info("Backup package validated: %s", target)
    return target


def create_rolling_backup_package(source: Path, uploads_dir: Path, rolling_dir: Path, now=None) -> Path:
    """Create, validate, then retain the newest rolling ZIP packages."""
    package = create_backup_package(source, uploads_dir, rolling_dir, now=now)
    _prune_validated(rolling_dir, ROLLING_PACKAGE_LIMIT, suffix=".zip")
    return package


def validate_backup_package(package_path: Path) -> dict:
    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path) as package:
            names = package.namelist()
            if package.testzip() is not None or "manifest.json" not in names:
                raise ValueError("Backup package is corrupt or incomplete")
            for name in names:
                pure = Path(name)
                if pure.is_absolute() or ".." in pure.parts:
                    raise ValueError("Backup package contains an unsafe path")
            manifest = json.loads(package.read("manifest.json"))
            if manifest.get("format_version") != 2 or manifest.get("database_filename") != "joshs_corner.db":
                raise ValueError("Backup manifest is invalid")
            listed = manifest.get("files", [])
            for item in listed:
                name = item.get("path", "")
                if name not in names or _checksum_stream(package.open(name)) != item.get("sha256"):
                    raise ValueError("Backup package checksum validation failed")
            if "joshs_corner.db" not in names:
                raise ValueError("Backup package has no database")
            with tempfile.TemporaryDirectory(prefix="joshs_corner_verify_") as temporary_name:
                database = Path(temporary_name) / "database.db"; database.write_bytes(package.read("joshs_corner.db"))
                if not integrity_check(database):
                    raise ValueError("Backup package database failed integrity checking")
            return manifest
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("Backup package is invalid") from error


def _checksum_stream(source) -> str:
    digest = hashlib.sha256()
    with source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integrity_check(path: Path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    connection = None
    try:
        connection = sqlite3.connect(path)
        return connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.DatabaseError:
        return False
    finally:
        if connection is not None:
            connection.close()


def create_backup(source: Path, backup_dir: Path, secondary_dir: Path | None = None, now=None, reuse_recent=False) -> Path:
    source, backup_dir = Path(source), Path(backup_dir)
    if not source.exists():
        raise FileNotFoundError(f"Database does not exist: {source}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    if reuse_recent:
        recent = sorted(backup_dir.glob("joshs_corner_*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
        if recent and (datetime.now().timestamp() - recent[0].stat().st_mtime) < 60 and integrity_check(recent[0]):
            return recent[0]
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    target = backup_dir / f"joshs_corner_{stamp}.db"
    suffix = 1
    while target.exists():
        target = backup_dir / f"joshs_corner_{stamp}_{suffix}.db"; suffix += 1
    try:
        live, copy = sqlite3.connect(source), sqlite3.connect(target)
        try:
            live.backup(copy)
        finally:
            copy.close()
            live.close()
        if not integrity_check(target):
            target.unlink(missing_ok=True)
            raise RuntimeError("Backup integrity check failed")
    except Exception:
        LOGGER.exception("Database backup failed")
        raise
    LOGGER.info("Database backup validated: %s", target)
    if secondary_dir:
        try:
            destination = Path(secondary_dir); destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination / target.name)
        except Exception:
            LOGGER.exception("Secondary backup copy failed; local backup remains valid")
    return target


def create_scheduled_backups(source: Path, backup_root: Path, secondary_monthly: Path | None = None, now=None, uploads_dir: Path | None = None):
    """Create a rolling backup every three days and one monthly archive at most."""
    now = now or datetime.now()
    root = Path(backup_root); rolling, monthly = root / "rolling", root / "monthly"
    rolling.mkdir(parents=True, exist_ok=True); monthly.mkdir(parents=True, exist_ok=True)
    uploads_dir = Path(uploads_dir) if uploads_dir else Path(source).parent / "uploads"
    latest = sorted(rolling.glob("joshs_corner_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    rolling_backup = None
    if not latest or now.timestamp() - latest[0].stat().st_mtime >= 3 * 86400:
        rolling_backup = create_rolling_backup_package(source, uploads_dir, rolling, now=now)
    month_prefix = f"joshs_corner_backup_{now:%Y-%m}-"
    monthly_backup = next(
        (path for path in sorted(monthly.glob(month_prefix + "*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
         if _is_valid_backup(path)),
        None,
    )
    if monthly_backup is None:
        monthly_backup = create_backup_package(source, uploads_dir, monthly, now=now)
        _prune_validated(monthly, MONTHLY_PACKAGE_LIMIT, suffix=".zip")
    if secondary_monthly:
        try:
            destination = Path(secondary_monthly); destination.mkdir(parents=True, exist_ok=True)
            secondary_backup = destination / monthly_backup.name
            if not secondary_backup.exists():
                shutil.copy2(monthly_backup, secondary_backup)
                LOGGER.info("Monthly secondary copy written locally: %s (cloud sync unconfirmed)", secondary_backup)
            else:
                LOGGER.info("Monthly secondary copy already present locally: %s (cloud sync unconfirmed)", secondary_backup)
        except Exception:
            LOGGER.exception("Monthly secondary copy failed; local monthly backup remains valid")
    return rolling_backup, monthly_backup


def _is_valid_backup(path: Path) -> bool:
    if path.suffix == ".db":
        return integrity_check(path)
    try:
        validate_backup_package(path)
        return True
    except ValueError:
        return False


def _prune_validated(directory: Path, limit: int, suffix: str | None = None):
    valid = sorted((p for p in Path(directory).glob("joshs_corner_*") if (suffix is None or p.suffix == suffix) and _is_valid_backup(p)), key=lambda p: p.stat().st_mtime)
    while len(valid) > limit and len(valid) > 1:
        oldest = valid.pop(0)
        oldest.unlink()
        LOGGER.info("Removed validated expired backup: %s", oldest)


def apply_retention(backup_dir: Path, now=None) -> list[Path]:
    """Keep 30 daily, 12 weekly, and every monthly representative; return deletion candidates."""
    files = sorted(Path(backup_dir).glob("joshs_corner_*.db"), reverse=True)
    if len(files) <= 1: return []
    current = (now or datetime.now()).date(); keep, weeks, months = set(), set(), set()
    for path in files:
        date_part = path.name.split("_")[2]
        try: day = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError: keep.add(path); continue
        if (current - day).days < 30: keep.add(path); continue
        week, month = day.isocalendar()[:2], (day.year, day.month)
        if week not in weeks and len(weeks) < 12: keep.add(path); weeks.add(week)
        elif month not in months: keep.add(path); months.add(month)
    return [path for path in files if path not in keep]


def restore_backup(source: Path, target: Path, replace_live: bool = False, safety_backup_dir: Path | None = None, uploads_target: Path | None = None) -> Path:
    source, target = Path(source), Path(target)
    if source.suffix.lower() == ".zip":
        return restore_backup_package(source, target, uploads_target, replace_live, safety_backup_dir)
    if not source.exists() or not integrity_check(source): raise ValueError("Selected backup is missing or invalid")
    if target.exists() and not replace_live:
        raise PermissionError("Refusing to replace a database without explicit force")
    if replace_live:
        if safety_backup_dir is None: raise PermissionError("A safety backup directory is required for live replacement")
        create_backup(target, safety_backup_dir)
    temporary = target.with_suffix(target.suffix + ".tmp") if replace_live else target
    incoming = sqlite3.connect(source)
    restored = sqlite3.connect(temporary)
    try:
        incoming.backup(restored)
    finally:
        restored.close()
        incoming.close()
    if not integrity_check(temporary): temporary.unlink(missing_ok=True); raise RuntimeError("Restored database failed integrity check")
    if replace_live:
        os.replace(temporary, target)
    return target


def restore_backup_package(source: Path, target: Path, uploads_target: Path | None = None, replace_live: bool = False, safety_backup_dir: Path | None = None) -> Path:
    """Restore a verified backup package into a separate location by default."""
    manifest = validate_backup_package(source)
    target = Path(target)
    uploads_target = Path(uploads_target) if uploads_target else target.parent / "uploads"
    if (target.exists() or uploads_target.exists()) and not replace_live:
        raise PermissionError("Refusing to replace a restore target without explicit force")
    if replace_live:
        if safety_backup_dir is None:
            raise PermissionError("A safety backup directory is required for live replacement")
        create_backup(target, safety_backup_dir)
    temporary_root = Path(tempfile.mkdtemp(prefix="joshs_corner_restore_"))
    try:
        database_temp = temporary_root / "joshs_corner.db"
        uploads_temp = temporary_root / "uploads"
        with zipfile.ZipFile(source) as package:
            database_temp.write_bytes(package.read("joshs_corner.db"))
            for item in manifest["files"]:
                relative = Path(item["path"])
                if relative.parts[:1] != ("uploads",):
                    continue
                destination = uploads_temp / Path(*relative.parts[1:])
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(package.read(item["path"]))
        if not integrity_check(database_temp):
            raise RuntimeError("Restored database failed integrity checking")
        if not replace_live:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(database_temp), target)
            if uploads_temp.exists(): shutil.move(str(uploads_temp), uploads_target)
        else:
            database_replacement = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(database_temp, database_replacement)
            os.replace(database_replacement, target)
            if uploads_target.exists():
                raise PermissionError("Live upload replacement requires a separately prepared empty target")
            if uploads_temp.exists(): shutil.move(str(uploads_temp), uploads_target)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    return target
