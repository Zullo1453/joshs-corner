from pathlib import Path

from app import create_app
from app.attachments import LocalStorageBackend
from app.runtime import RuntimePaths, configured_database_uri, local_database_uri
from app.search import SQLiteSearchAdapter, UniversalSearchService


def test_default_database_url_remains_the_existing_local_sqlite_path(tmp_path):
    instance = tmp_path / "instance"
    assert configured_database_uri(instance, {}) == local_database_uri(instance)
    assert configured_database_uri(instance, {"DATABASE_URL": "sqlite:///:memory:"}) == "sqlite:///:memory:"


def test_runtime_paths_categorise_local_durable_and_disposable_locations(tmp_path):
    paths = RuntimePaths.for_project(tmp_path)
    assert paths.local_database == tmp_path / "instance" / "joshs_corner.db"
    assert paths.uploads == tmp_path / "instance" / "uploads"
    assert paths.backups == tmp_path / "backups"
    assert paths.on_this_day_cache.parent == paths.instance
    assert not paths.instance.exists()


def test_local_storage_backend_uses_name_only_paths_and_is_disposable(tmp_path):
    backend = LocalStorageBackend(tmp_path / "uploads")
    path = backend.write("../../safe.webp", b"image")
    assert path == tmp_path / "uploads" / "safe.webp"
    assert backend.exists("safe.webp") and backend.files() == [path]
    backend.delete("safe.webp")
    assert not backend.exists("safe.webp")


def test_repeated_app_creation_does_not_call_backup_lifecycle(monkeypatch, tmp_path):
    calls = []

    def fail_if_called(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("backup lifecycle must not run during app startup")

    monkeypatch.setattr("app.backup.create_scheduled_backups", fail_if_called)
    for _ in range(3):
        app = create_app({
            "TESTING": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
        })
        assert app.config["RUNTIME_PATHS"].local_database.name == "joshs_corner.db"
    assert calls == []


def test_local_search_selects_the_sqlite_adapter(app):
    with app.app_context():
        assert isinstance(UniversalSearchService()._adapter(), SQLiteSearchAdapter)