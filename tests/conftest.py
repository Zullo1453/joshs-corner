import pytest

from app import create_app
from app.extensions import db


class OfflineHistoryService:
    def get_event(self, selected_date):
        return None


class OfflineFigureService:
    def get_figure(self, selected_date):
        return None


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "ON_THIS_DAY_SERVICE": OfflineHistoryService(),
            "FIGURE_OF_DAY_SERVICE": OfflineFigureService(),
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
