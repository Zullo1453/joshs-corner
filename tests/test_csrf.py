import pytest

from app import create_app
from app.extensions import db


def test_csrf_rejects_missing_or_invalid_post_tokens():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": True})
    with app.app_context(): db.create_all()
    client = app.test_client()
    assert client.get("/journal/").status_code == 200
    assert client.post("/todos/new", data={"text": "blocked"}).status_code == 400
    assert client.post("/todos/new", data={"text": "blocked", "csrf_token": "invalid"}).status_code == 400
    with app.app_context(): db.drop_all()


@pytest.mark.parametrize("endpoint", [
    "/journal/entry/2026-07-12",
    "/notes/new",
    "/todos/new",
    "/games/new",
    "/watchlist/new",
    "/reading/new",
])
def test_csrf_protects_every_section(endpoint):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": True})
    with app.app_context(): db.create_all()
    assert app.test_client().post(endpoint, data={}).status_code == 400
    with app.app_context(): db.drop_all()
