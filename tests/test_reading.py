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


def test_reading_detail_fragment_reuses_editor_and_missing_books_are_safe(client, app):
    book_id = add_book(app, "Fragment book", format="Written", status="Reading", book_type="fiction", notes="A fragment note")
    full_page = client.get(f"/reading/?book_id={book_id}")
    fragment = client.get(f"/reading/detail/{book_id}")
    assert full_page.status_code == 200
    assert b"data-reading-detail-slot" in full_page.data
    assert b"book-sidebar" in full_page.data
    assert f"/reading/?book_id={book_id}".encode() in full_page.data
    assert fragment.status_code == 200
    assert b"data-book-editor" in fragment.data
    assert b"Fragment book" in fragment.data
    assert b"book-sidebar" not in fragment.data
    assert b"<!doctype html>" not in fragment.data.lower()
    assert client.get("/reading/detail/999999").status_code == 404


def test_reading_detail_fragment_validates_filters(client, app):
    book_id = add_book(app, "Filtered fragment", format="Written", status="Reading", book_type="fiction")
    assert client.get(f"/reading/detail/{book_id}?type=fiction").status_code == 200
    assert client.get(f"/reading/detail/{book_id}?type=not-a-type").status_code == 400


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


def test_autosave_updates_only_the_selected_book_and_sanitises_notes(client, app):
    selected_id = add_book(app, "Selected", format="Written", status="To Read", book_type="fiction", notes="Before")
    other_id = add_book(app, "Other", format="Audible", status="Reading", book_type="non_fiction", notes="Unchanged")
    response = client.post(
        f"/reading/{selected_id}/autosave",
        json=book_data(
            title="Selected",
            format="Audible",
            book_type="non_fiction",
            status="Finished",
            rating="4.5",
            release_date="2024-01-05",
            notes="<p>Safe <script>bad()</script>notes</p>",
        ),
    )
    assert response.status_code == 200 and response.json["status"] == "saved"
    with app.app_context():
        selected = db.session.get(ReadingItem, selected_id)
        other = db.session.get(ReadingItem, other_id)
        assert (selected.format, selected.book_type, selected.status, selected.rating) == ("Audible", "non_fiction", "Finished", 4.5)
        assert selected.release_date == date(2024, 1, 5)
        assert "script" not in selected.notes and "Safe" in selected.notes
        assert other.notes == "Unchanged"
        assert ReadingItem.query.count() == 2


def test_autosave_rejects_invalid_or_malformed_data_without_writing(client, app):
    book_id = add_book(app, "Stable", format="Written", status="To Read", book_type="fiction", notes="Original")
    invalid = client.post(f"/reading/{book_id}/autosave", json=book_data(title="Stable", rating="3.2"))
    malformed = client.post(f"/reading/{book_id}/autosave", json=["not", "a", "book"])
    assert invalid.status_code == 400 and invalid.json["status"] == "error"
    assert malformed.status_code == 400 and malformed.json["status"] == "error"
    with app.app_context():
        assert db.session.get(ReadingItem, book_id).notes == "Original"


def test_reading_autosave_client_and_scrollbar_are_reading_specific():
    script = open("app/static/js/reading.js", encoding="utf-8").read()
    stylesheet = open("app/static/css/reading_autosave.css", encoding="utf-8").read()
    assert "autosave" in script and "X-CSRFToken" in script
    assert "setTimeout(flushAutosave, delay)" in script
    assert "Saving…" in script and "Save failed" in script and "Offline / retrying" in script
    assert ".reading-page .book-list" in stylesheet
    assert "::-webkit-scrollbar" in stylesheet and "scrollbar-color" in stylesheet
    assert ".notes-list" not in stylesheet and ".watch-list" not in stylesheet


def test_reading_hybrid_save_initialises_helpers_before_using_them():
    script = open("app/static/js/reading.js", encoding="utf-8").read()
    assert script.index("const syncNotes") < script.index("syncNotes();")
    assert "manualSnapshot" in script and "textDirty" in script
    assert "Leave without saving?" in script and "beforeunload" in script


def test_reading_partial_navigation_client_is_scoped_and_progressive():
    script = open("app/static/js/reading.js", encoding="utf-8").read()
    assert "[data-sidebar-module='reading']" in script
    assert "data-reading-detail-slot" in script
    assert "fetch(partial" in script
    assert "history.pushState" in script and '"popstate"' in script
    assert "slot.innerHTML" in script
    assert "setSelectedBook" in script
    assert "You have unsaved changes. Leave without saving?" in script
    assert "event.metaKey" in script and "event.ctrlKey" in script and "event.shiftKey" in script and "event.altKey" in script
    assert "link.hasAttribute(\"download\")" in script and "!link.target" in script
    assert "scrollIntoView" not in script
    assert "reading-navigation-error" in script and "Open normally" in script
    assert "manualSnapshot" in script and "title: manualSnapshot.title" in script


def test_reading_rich_text_can_initialise_a_replaced_detail_panel_once():
    script = open("app/static/js/rich_text.js", encoding="utf-8").read()
    assert "const initialise = (scope = document)" in script
    assert "scope.querySelectorAll('textarea[name=\"notes\"]')" in script
    assert "window.JoshsCornerRichText = { initialise, destroy }" in script
    assert "if (root.dataset.ready) return" in script
    assert "cleanups = new WeakMap" in script
    assert "JoshsCornerRichText?.destroy(slot)" in open("app/static/js/reading.js", encoding="utf-8").read()


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
