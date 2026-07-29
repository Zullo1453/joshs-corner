from datetime import date
from pathlib import Path

from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import ReadingItem


def add_book(app, title="Book", **values):
    with app.app_context():
        book = ReadingItem(title=title, **values)
        db.session.add(book)
        db.session.commit()
        return book.id


def book_data(**overrides):
    values = {
        "title": "Thinking, Fast and Slow",
        "format": "Written",
        "book_type": "non_fiction",
        "release_date": "2011-10-25",
        "status": "Finished",
        "rating": "4.5",
        "notes": "Useful ideas about decision-making.",
    }
    values.update(overrides)
    return values


def test_reading_page_loads_with_empty_state(client):
    response = client.get("/reading/")
    assert response.status_code == 200
    assert b"Add Book" in response.data and b"Your reading list is empty." in response.data


def test_create_fiction_and_non_fiction_books(client, app):
    client.post("/reading/new", data=book_data(title="The Archive of Ash", book_type="fiction"))
    client.post("/reading/new", data=book_data(title="The Wager", format="Audible", status="Reading", book_type="non_fiction"))
    with app.app_context():
        books = {book.title: (book.format, book.book_type) for book in ReadingItem.query.all()}
    assert books == {"The Archive of Ash": ("Written", "fiction"), "The Wager": ("Audible", "non_fiction")}


def test_update_and_legacy_unclassified_books(client, app):
    book_id = add_book(app, "Before", format="Written", status="To Read", book_type="fiction", notes="Kept notes")
    updated = client.post(f"/reading/{book_id}", data=book_data(title="After", book_type="non_fiction", notes="Kept notes"), follow_redirects=True)
    assert b"Non-Fiction" in updated.data
    legacy_id = add_book(app, "Legacy", format="Audible", status="Reading", notes="Existing rich text notes")
    legacy = client.get(f"/reading/?book_id={legacy_id}")
    assert b"Unclassified" in legacy.data and b"Existing rich text notes" in legacy.data
    response = client.post(f"/reading/{legacy_id}", data=book_data(title="Legacy", format="Audible", status="Reading", book_type="", notes="Existing rich text notes"), follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(ReadingItem, legacy_id).book_type is None


def test_blank_title_delete_and_invalid_classification_preserves_selection(client, app):
    response = client.post("/reading/new", data=book_data(title="  "))
    assert response.status_code == 400 and b"book title is required" in response.data
    invalid = client.post("/reading/new", data=book_data(book_type="fiction", rating="3.2"))
    assert invalid.status_code == 400
    assert b"half-star increments" in invalid.data and b'value="fiction" selected' in invalid.data
    invalid_type = client.post("/reading/new", data=book_data(book_type="unknown"))
    assert invalid_type.status_code == 400 and b"Choose Fiction or Non-Fiction" in invalid_type.data
    book_id = add_book(app, "Delete", format="Written", status="To Read", book_type="fiction")
    client.post(f"/reading/{book_id}/delete")
    with app.app_context():
        assert db.session.get(ReadingItem, book_id) is None


def test_type_filters_work_with_existing_filters_and_no_results(client, app):
    add_book(app, "Fiction", format="Written", status="Finished", rating=4.5, book_type="fiction", notes="Story notes")
    add_book(app, "Non-fiction", format="Audible", status="Reading", rating=4, book_type="non_fiction", notes="Research notes")
    add_book(app, "Legacy", format="Written", status="To Read", rating=3, notes="Old notes")
    assert b"Fiction" in client.get("/reading/?type=fiction").data
    assert b"Non-fiction" in client.get("/reading/?type=non_fiction").data
    assert b"Legacy" in client.get("/reading/?type=unclassified").data
    filtered = client.get("/reading/?format=Written&type=fiction&status=Finished&rating=4&q=story")
    assert b"Fiction" in filtered.data and b"Non-fiction" not in filtered.data
    no_results = client.get("/reading/?format=Audible&type=fiction")
    assert b"No books match these filters." in no_results.data


def test_optional_release_dates_notes_and_rich_preview_are_preserved(client, app):
    client.post("/reading/new", data=book_data(title="No date", release_date="", notes="<p>Useful <strong>idea</strong></p>"))
    client.post("/reading/new", data=book_data(title="Dated", release_date="2011-10-25", book_type="fiction"))
    page = client.get("/reading/")
    with app.app_context():
        dates = {book.title: book.release_date for book in ReadingItem.query.all()}
    assert dates == {"No date": None, "Dated": date(2011, 10, 25)}
    assert b"Useful idea" in page.data and b"&lt;strong&gt;" not in page.data


def test_invalid_values_missing_book_and_interface_assets(client):
    for data, message in (
        (book_data(release_date="bad-date"), b"valid release date"),
        (book_data(rating="3.2"), b"half-star increments"),
        (book_data(format="Kindle"), b"Written or Audible"),
        (book_data(status="Paused"), b"valid reading status"),
    ):
        response = client.post("/reading/new", data=data)
        assert response.status_code == 400 and message in response.data
    assert client.post("/reading/999999").status_code == 404
    assert client.post("/reading/999999/delete").status_code == 404
    page = client.get("/reading/new")
    assert b"data-book-stars" in page.data
    assert b"All types" in page.data and b"Non-Fiction" in page.data


def test_book_type_migration_preserves_legacy_records_and_reverses(tmp_path):
    database = tmp_path / "reading-migration.db"
    migration_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}"})
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with migration_app.app_context():
        upgrade(directory=str(migrations), revision="c4d8e1f1a921")
        db.session.execute(text("INSERT INTO reading_item (title, format, status, notes, created_at, updated_at) VALUES ('Legacy book', 'Written', 'To Read', 'Existing notes', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.commit()
        upgrade(directory=str(migrations), revision="head")
        row = db.session.execute(text("SELECT title, notes, book_type FROM reading_item")).one()
        assert row == ("Legacy book", "Existing notes", None)
        assert "book_type" in {column["name"] for column in inspect(db.engine).get_columns("reading_item")}
        downgrade(directory=str(migrations), revision="c4d8e1f1a921")
        assert "book_type" not in {column["name"] for column in inspect(db.engine).get_columns("reading_item")}
