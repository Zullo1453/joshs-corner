"""Disposable, fictional browser-verification server; never opens the live DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.extensions import db
from app.models import Note
from conftest import OfflineFigureService, OfflineHistoryService
from test_search import DAY, seed_records

app = create_app({
    "TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "ON_THIS_DAY_SERVICE": OfflineHistoryService(),
    "FIGURE_OF_DAY_SERVICE": OfflineFigureService(), "SEARCH_TODAY": DAY,
    "TODOS_TODAY": DAY,
})
with app.app_context():
    db.create_all()
    seed_records()
    db.session.add_all([Note(title=f"Scrolling sample {i}", body="A fictional search result.") for i in range(45)])
    db.session.add(Note(title='<img src=x onerror=alert(1)> Safety sample', body="<p>Safe visible text</p>"))
    db.session.commit()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5011, use_reloader=False, debug=False)
