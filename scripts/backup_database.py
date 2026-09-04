import os
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from app.backup import create_scheduled_backups
from app.runtime import RuntimePaths

paths = RuntimePaths.for_project(root)

local_config = paths.instance / "local_config.py"
config = runpy.run_path(str(local_config)) if local_config.exists() else {}
secondary = os.environ.get("JOSHS_CORNER_BACKUP_SECONDARY_DIR") or config.get("BACKUP_SECONDARY_DIR")
print(create_scheduled_backups(
    paths.local_database,
    paths.backups,
    Path(secondary) if secondary else None,
))
