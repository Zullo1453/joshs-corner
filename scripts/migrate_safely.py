import subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from app.backup import _prune_validated, create_backup

rolling_backups = root / "backups" / "rolling"
create_backup(root / "instance" / "joshs_corner.db", rolling_backups)
_prune_validated(rolling_backups, 10)
raise SystemExit(subprocess.call([sys.executable, "-m", "flask", "--app", "run.py", "db", "upgrade"], cwd=root))
