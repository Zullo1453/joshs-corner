from pathlib import Path
import subprocess, sys
from app.backup import create_backup
root = Path(__file__).resolve().parents[1]
create_backup(root / "instance" / "joshs_corner.db", root / "backups")
raise SystemExit(subprocess.call([sys.executable, "-m", "flask", "--app", "run.py", "db", "upgrade"], cwd=root))
