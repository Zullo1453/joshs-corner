"""Fictional in-memory Exercise browser fixture. Never opens the live DB."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.extensions import db
from app.models import Exercise
from conftest import OfflineFigureService, OfflineHistoryService
from test_gym import add_occurrence

DAY = date(2026, 9, 2)
app = create_app({
    'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'ON_THIS_DAY_SERVICE': OfflineHistoryService(), 'FIGURE_OF_DAY_SERVICE': OfflineFigureService(),
    'EXERCISE_TODAY': DAY, 'SEARCH_TODAY': DAY, 'TODOS_TODAY': DAY,
})
with app.app_context():
    db.create_all()
    for index, name in enumerate(['Fictional Press', 'Fictional Raise', 'Fictional Fly', 'Fictional Curl']):
        item = Exercise(name=name, body_part='Shoulders', sort_order=index)
        db.session.add(item)
        db.session.commit()
        if index == 0:
            add_occurrence(item, DAY-timedelta(days=3), [(20,10),(22.5,6),(25,4)])
            add_occurrence(item, DAY-timedelta(days=1), [(20,10)]*3)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5012, use_reloader=False, debug=False)
