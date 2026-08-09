from datetime import date
from pathlib import Path

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import create_app
from app.backup import create_backup_package, restore_backup, validate_backup_package
from app.extensions import db
from app.models import Automation, AutomationRun, FlightOffer, FlightTracker


FUTURE_FORM = {
    "name": "Long-haul practice search",
    "outbound_origin": " aaa ", "outbound_destination": "bbb", "outbound_date": "2035-05-10",
    "return_origin": "bbb", "return_destination": "aaa", "return_date": "2035-05-20",
    "adults": "1", "cabin_class": "economy", "currency": "aud", "target_price": "1234.56",
    "primary_max_duration_hours": "30", "primary_max_stops": "2", "secondary_enabled": "on",
}


def create_tracker(client, overrides=None):
    form = FUTURE_FORM | (overrides or {})
    return client.post("/automations/trackers/new", data=form, follow_redirects=False)


def get_tracker():
    return db.session.scalar(db.select(FlightTracker))


def test_creates_valid_tracker_transactionally_and_normalizes_form(client, app):
    response = create_tracker(client)
    assert response.status_code == 302
    with app.app_context():
        tracker = get_tracker()
        assert tracker.automation.name == "Long-haul practice search"
        assert (tracker.outbound_origin, tracker.outbound_destination, tracker.currency) == ("AAA", "BBB", "AUD")
        assert tracker.target_price_cents == 123456
        assert tracker.primary_max_duration_minutes == 1800
        assert tracker.automation.status == "active"


@pytest.mark.parametrize("overrides, message", [
    ({"name": ""}, b"Give this tracker a name."),
    ({"outbound_origin": "too-long"}, b"Use a three-letter airport or metropolitan code."),
    ({"outbound_destination": "AAA"}, b"Outbound origin and destination must differ."),
    ({"return_date": "2035-05-01"}, b"Return date cannot be before the outbound date."),
    ({"target_price": "0"}, b"Enter a positive target price."),
    ({"primary_max_duration_hours": "0"}, b"Choose a maximum journey duration between 1 and 168."),
    ({"primary_max_stops": "-1"}, b"Choose a maximum stop count between 0 and 6."),
])
def test_invalid_tracker_forms_create_no_orphan_records(client, app, overrides, message):
    response = create_tracker(client, overrides)
    assert response.status_code == 400 and message in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Automation.id))) == 0
        assert db.session.scalar(db.select(db.func.count(FlightTracker.id))) == 0


def test_editing_preferences_keeps_series_but_material_change_advances_it(client, app):
    create_tracker(client)
    with app.app_context():
        tracker = get_tracker()
        tracker_id = tracker.id
        run = AutomationRun(automation=tracker.automation, status="succeeded", configuration_version=1)
        run.offers.append(FlightOffer(tracker=tracker, configuration_version=1, category="primary", total_price_cents=100000,
                                      currency="AUD", outbound_duration_minutes=1200, return_duration_minutes=1200,
                                      outbound_stops=1, return_stops=1, fingerprint="a" * 64))
        db.session.add(run); db.session.commit()
    first = FUTURE_FORM | {"name": "Renamed", "target_price": "1200.00", "primary_max_duration_hours": "28"}
    assert client.post(f"/automations/trackers/{tracker_id}/edit", data=first).status_code == 302
    with app.app_context():
        tracker = db.get_or_404(FlightTracker, tracker_id)
        assert tracker.configuration_version == 1 and tracker.automation.name == "Renamed"
    material = first | {"outbound_date": "2035-05-11"}
    assert client.post(f"/automations/trackers/{tracker_id}/edit", data=material).status_code == 302
    with app.app_context():
        tracker = db.get_or_404(FlightTracker, tracker_id)
        assert tracker.configuration_version == 2
        assert db.session.scalar(db.select(db.func.count(FlightOffer.id))) == 1


def test_tracker_lifecycle_preserves_history_and_restores_paused(client, app):
    create_tracker(client)
    with app.app_context(): tracker_id = get_tracker().id
    assert client.post(f"/automations/trackers/{tracker_id}/pause").status_code == 302
    assert client.post(f"/automations/trackers/{tracker_id}/check-now").status_code == 409
    assert client.post(f"/automations/trackers/{tracker_id}/resume").status_code == 302
    assert client.post(f"/automations/trackers/{tracker_id}/archive").status_code == 302
    assert client.post(f"/automations/trackers/{tracker_id}/check-now").status_code == 409
    assert client.post(f"/automations/trackers/{tracker_id}/restore").status_code == 302
    with app.app_context(): assert db.get_or_404(FlightTracker, tracker_id).automation.status == "paused"


def test_tracker_pages_and_provider_not_configured_message(client):
    created = create_tracker(client)
    tracker_path = created.headers["Location"]
    assert b"Long-haul practice search" in client.get("/automations").data
    assert b"Flight Trackers" in client.get("/automations/trackers").data
    detail = client.get(tracker_path)
    assert b"No Primary results yet." in detail.data and b"No Secondary results yet." in detail.data
    response = client.post(tracker_path + "/check-now", follow_redirects=True)
    assert b"Flight provider not configured" in response.data


def test_flight_tracker_migration_preserves_stage_3a_data_and_reverses(tmp_path):
    database = tmp_path / "flight-migration.db"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with app.app_context():
        upgrade(directory=str(migrations), revision="9a7b3c5d8e10")
        db.session.execute(text("INSERT INTO automation (name, automation_type, status, created_at, updated_at) VALUES ('Old', 'generic', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.commit(); upgrade(directory=str(migrations), revision="head")
        assert db.session.execute(text("SELECT name FROM automation")).scalar_one() == "Old"
        assert {"flight_tracker", "flight_offer"}.issubset(inspect(db.engine).get_table_names())
        downgrade(directory=str(migrations), revision="9a7b3c5d8e10")
        assert "flight_tracker" not in inspect(db.engine).get_table_names()
        upgrade(directory=str(migrations), revision="head")
        assert {"flight_tracker", "flight_offer"}.issubset(inspect(db.engine).get_table_names())


def test_backup_restore_includes_tracker_runs_and_offers(tmp_path):
    database = tmp_path / "flight-live.db"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    with app.app_context():
        db.create_all()
        automation = Automation(name="Fixture tracker", automation_type="flight_tracker")
        tracker = FlightTracker(automation=automation, outbound_origin="AAA", outbound_destination="BBB", outbound_date=date(2035, 5, 10), return_origin="BBB", return_destination="AAA", return_date=date(2035, 5, 20), target_price_cents=100000, primary_max_duration_minutes=1200, primary_max_stops=2)
        run = AutomationRun(automation=automation, status="succeeded", configuration_version=1)
        run.offers.append(FlightOffer(tracker=tracker, configuration_version=1, category="primary", total_price_cents=99999, currency="AUD", outbound_duration_minutes=1000, return_duration_minutes=1100, outbound_stops=1, return_stops=1, fingerprint="b" * 64))
        db.session.add(automation); db.session.commit()
    package = create_backup_package(database, tmp_path / "uploads", tmp_path / "backups")
    validate_backup_package(package); restored = tmp_path / "restored.db"; restore_backup(package, restored)
    import sqlite3
    with sqlite3.connect(restored) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT count(*) FROM flight_offer").fetchone()[0] == 1
