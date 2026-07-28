from pathlib import Path
from app.backup import create_backup
root = Path(__file__).resolve().parents[1]
print(create_backup(root / "instance" / "joshs_corner.db", root / "backups"))
