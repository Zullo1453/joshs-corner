import argparse
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from app.backup import restore_backup

parser = argparse.ArgumentParser(); parser.add_argument("backup"); parser.add_argument("--target", default="restore.test.db"); parser.add_argument("--uploads-target"); parser.add_argument("--replace-live", action="store_true")
args = parser.parse_args()
target = root / "instance" / "joshs_corner.db" if args.replace_live else Path(args.target)
uploads_target = Path(args.uploads_target) if args.uploads_target else (root / "instance" / "uploads" if args.replace_live else Path(args.target).parent / "restored_uploads")
print(restore_backup(Path(args.backup), target, args.replace_live, root / "backups" if args.replace_live else None, uploads_target))
