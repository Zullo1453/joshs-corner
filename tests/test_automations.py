import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import create_app
from app.backup import create_backup_package, create_scheduled_backups, restore_backup, validate_backup_package
from app.extensions import db
from app.models import Automation, AutomationRun, CurrencyPair, WeatherLocation


HUB_PATHS = ("/", "/journal/", "/notes/", "/todos/", "/games/", "/watchlist/", "/reading/")
AUTOMATION_PATHS = ("/automations", "/automations/weather", "/automations/currency", "/automations/health")


def test_shared_navigation_identifies_hub_and_links_top_level_sections(client):
    for path in HUB_PATHS:
        response = client.get(path)
        assert response.status_code == 200
        assert b'href="/" class="is-active" aria-current="page"' in response.data
        assert b'href="/automations"' in response.data
        assert b">Intelligence</span>" in response.data
        assert b'application-nav__icon' in response.data
        assert b'application-nav__radar' in response.data
        assert b"Automations</span>" not in response.data
        assert b'aria-label="Future sections"' in response.data
        future_markup = response.data.split(b'aria-label="Future sections"', 1)[1].split(b"</span>", 2)[0]
        assert b"href=" not in future_markup


def test_intelligence_routes_identify_the_section_and_render_real_empty_states(client):
    expected = {
        "/automations": b"No saved locations yet",
        "/automations/weather": b"No saved locations",
        "/automations/currency": b"No saved currency pairs",
        "/automations/health": b"Josh's Corner Health",
    }
    for path, copy in expected.items():
        response = client.get(path)
        assert response.status_code == 200
        assert b'href="/automations" class="is-active" aria-current="page"' in response.data
        assert copy in response.data


def test_intelligence_subnavigation_links_and_active_states(client):
    response = client.get("/automations/weather")
    for href in (b'/automations', b'/automations/weather', b'/automations/currency', b'/automations/health'):
        assert b'href="' + href + b'"' in response.data
    assert b'href="/automations/weather" class="is-active" aria-current="page"' in response.data


def test_home_icon_is_contextual_for_hub_and_intelligence(client):
    journal = client.get("/journal/")
    assert b'href="/" aria-label="Hub home" title="Hub home"' in journal.data
    weather = client.get("/automations/weather")
    assert b'href="/automations" aria-label="Intelligence home" title="Intelligence home"' in weather.data


def test_legacy_automation_placeholders_redirect_to_the_overview(client):
    for path in ("/automations/trackers", "/automations/alerts", "/automations/history"):
        response = client.get(path)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/automations")


def test_navigation_control_is_accessible_and_shared(client):
    response = client.get("/")
    assert b'<button class="application-nav__toggle" type="button"' in response.data
    assert b'aria-label="Open main navigation"' in response.data
    assert b'aria-controls="main-navigation-panel"' in response.data
    assert b'aria-expanded="false"' in response.data


def test_hub_and_intelligence_share_a_centred_rail_icon_wrapper():
    stylesheet = (Path(__file__).parents[1] / "app" / "static" / "css" / "application_nav.css").read_text(encoding="utf-8")
    assert ".application-nav__icon," in stylesheet
    assert "width: 38px; height: 42px; place-items: center;" in stylesheet


def test_jz_brand_returns_to_hub_and_hub_icon_has_windows(client):
    page = client.get("/gym/runs")
    assert b'href="/" aria-label="Josh\'s Corner Hub" title="Go to Hub"' in page.data
    assert b'application-nav__hub-icon' in page.data
    assert b'M7.2 11.2h2.1v2.1H7.2z' in page.data


@pytest.mark.parametrize("status", ("active", "paused", "archived"))
def test_automation_statuses_validate(app, status):
    with app.app_context():
        automation = Automation(name="Example", automation_type="tracker", status=status)
        db.session.add(automation)
        db.session.commit()
        assert automation.status == status


def test_invalid_automation_and_run_statuses_are_rejected(app):
    with app.app_context():
        with pytest.raises(ValueError):
            Automation(name="Example", automation_type="tracker", status="unknown")
        automation = Automation(name="Example", automation_type="tracker")
        with pytest.raises(ValueError):
            AutomationRun(automation=automation, status="unknown")


def test_deleting_an_automation_removes_its_run_history(app):
    with app.app_context():
        automation = Automation(name="Example", automation_type="tracker")
        automation.runs.append(AutomationRun(status="succeeded", summary="Done"))
        db.session.add(automation)
        db.session.commit()
        db.session.delete(automation)
        db.session.commit()
        assert db.session.scalar(db.select(db.func.count(AutomationRun.id))) == 0


def test_automation_migration_preserves_existing_data_and_reverses(tmp_path):
    database = tmp_path / "automation-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="268a59cac5dd")
        db.session.execute(text("INSERT INTO note (title, body, is_favourite, created_at, updated_at) VALUES ('Preserved', 'Existing body', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.commit()
        upgrade(directory=str(migrations), revision="head")
        assert db.session.execute(text("SELECT title, body FROM note")).one() == ("Preserved", "Existing body")
        assert {"automation", "automation_run"}.issubset(set(inspect(db.engine).get_table_names()))
        downgrade(directory=str(migrations), revision="268a59cac5dd")
        assert "automation" not in inspect(db.engine).get_table_names()
        assert db.session.execute(text("SELECT title, body FROM note")).one() == ("Preserved", "Existing body")


def test_backup_restore_naturally_includes_automation_tables(tmp_path):
    database = tmp_path / "live.db"
    backup_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    with backup_app.app_context():
        db.create_all()
        automation = Automation(name="Local tracker", automation_type="tracker", status="paused")
        automation.runs.append(AutomationRun(status="succeeded", summary="Checked"))
        db.session.add(automation)
        db.session.commit()
    package = create_backup_package(database, tmp_path / "uploads", tmp_path / "backups")
    validate_backup_package(package)
    restored = tmp_path / "restored.db"
    restore_backup(package, restored)
    with sqlite3.connect(restored) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT name, status FROM automation").fetchone() == ("Local tracker", "paused")
        assert connection.execute("SELECT summary FROM automation_run").fetchone()[0] == "Checked"


def test_backup_restore_naturally_includes_weather_and_currency_tables(tmp_path):
    database = tmp_path / "live.db"
    backup_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    with backup_app.app_context():
        db.create_all()
        db.session.add(WeatherLocation(display_name="Test place", latitude=1, longitude=2, timezone="UTC"))
        db.session.add(CurrencyPair(base_currency="AUD", quote_currency="EUR"))
        db.session.commit()
    package = create_backup_package(database, tmp_path / "uploads", tmp_path / "backups")
    restored = tmp_path / "restored.db"
    restore_backup(package, restored)
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT display_name FROM weather_location").fetchone()[0] == "Test place"
        assert connection.execute("SELECT base_currency, quote_currency FROM currency_pair").fetchone() == ("AUD", "EUR")


def test_rolling_and_monthly_backups_both_include_automation_tables(tmp_path):
    database = tmp_path / "live.db"
    backup_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    with backup_app.app_context():
        db.create_all()
    rolling, monthly = create_scheduled_backups(
        database, tmp_path / "scheduled", now=datetime(2026, 8, 9, 15, 0)
    )
    assert rolling is not None and monthly is not None
    for package in (rolling, monthly):
        validate_backup_package(package)
        restored = tmp_path / f"{package.parent.name}.db"
        restore_backup(package, restored)
        with sqlite3.connect(restored) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            assert {"automation", "automation_run"}.issubset(tables)
