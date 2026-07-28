"""SQLite backup, validation, retention, and non-destructive restore helpers."""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)


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


def create_scheduled_backups(source: Path, backup_root: Path, secondary_monthly: Path | None = None, now=None):
    """Create a rolling backup every three days and one monthly archive at most."""
    now = now or datetime.now()
    root = Path(backup_root); rolling, monthly = root / "rolling", root / "monthly"
    rolling.mkdir(parents=True, exist_ok=True); monthly.mkdir(parents=True, exist_ok=True)
    latest = sorted(rolling.glob("joshs_corner_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    rolling_backup = None
    if not latest or now.timestamp() - latest[0].stat().st_mtime >= 3 * 86400:
        rolling_backup = create_backup(source, rolling, now=now)
        _prune_validated(rolling, 10)
    month_prefix = f"joshs_corner_{now:%Y-%m}-"
    monthly_backup = next(
        (path for path in sorted(monthly.glob(month_prefix + "*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
         if integrity_check(path)),
        None,
    )
    if monthly_backup is None:
        monthly_backup = create_backup(source, monthly, now=now)
        _prune_validated(monthly, 12)
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


def _prune_validated(directory: Path, limit: int):
    valid = sorted((p for p in directory.glob("joshs_corner_*.db") if integrity_check(p)), key=lambda p: p.stat().st_mtime)
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


def restore_backup(source: Path, target: Path, replace_live: bool = False, safety_backup_dir: Path | None = None) -> Path:
    source, target = Path(source), Path(target)
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
