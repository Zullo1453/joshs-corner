import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from app import create_app
from app.attachments import attachment_diagnostics

app = create_app()
with app.app_context():
    print(json.dumps(attachment_diagnostics(), indent=2))
