from datetime import date

from app.extensions import db
from app.models import ReadingItem


def add_book(app, title="Book", **values):
    with app.app_context():
        book = ReadingItem(title=title, **values)
        db.session.add(book); db.session.commit()
        return book.id


def book_data(**overrides):
    values = {"title":"Thinking, Fast and Slow","format":"Written","release_date":"2011-10-25","status":"Finished","rating":"4.5","notes":"Useful ideas about decision-making."}
    values.update(overrides); return values


def test_reading_page_loads_with_empty_state(client):
    response = client.get("/reading/")
    assert response.status_code == 200
    assert b"Add Book" in response.data and b"Your reading list is empty." in response.data


def test_create_written_and_audible_books(client, app):
    client.post("/reading/new", data=book_data())
    client.post("/reading/new", data=book_data(title="The Wager", format="Audible", status="Reading"))
    with app.app_context(): assert {book.format for book in ReadingItem.query.all()} == {"Written", "Audible"}


def test_blank_title_update_and_delete(client, app):
    response = client.post("/reading/new", data=book_data(title="  "))
    assert response.status_code == 400 and b"book title is required" in response.data
    book_id = add_book(app, "Before", format="Written", status="To Read")
    assert b"After" in client.post(f"/reading/{book_id}", data=book_data(title="After", notes="Updated"), follow_redirects=True).data
    client.post(f"/reading/{book_id}/delete")
    with app.app_context(): assert db.session.get(ReadingItem, book_id) is None


def test_search_and_all_filters_work_together(client, app):
    add_book(app, "Thinking", format="Written", status="Finished", rating=4.5, notes="Anchoring and bias")
    add_book(app, "The Wager", format="Audible", status="Reading", rating=4, notes="Shipwreck notes")
    assert b"Thinking" in client.get("/reading/?q=thinking").data
    assert b"Thinking" in client.get("/reading/?q=anchoring").data
    filtered = client.get("/reading/?format=Written&status=Finished&rating=4&q=bias")
    assert b"Thinking" in filtered.data and b"The Wager" not in filtered.data
    assert b"The Wager" in client.get("/reading/?format=Audible").data
    assert b"Thinking" in client.get("/reading/?status=Finished").data
    assert b"Thinking" in client.get("/reading/?rating=4").data


def test_optional_and_valid_release_dates(client, app):
    client.post("/reading/new", data=book_data(title="No date", release_date=""))
    client.post("/reading/new", data=book_data(title="Dated", release_date="2011-10-25"))
    with app.app_context():
        dates = {book.title: book.release_date for book in ReadingItem.query.all()}
        assert dates == {"No date": None, "Dated": date(2011, 10, 25)}


def test_invalid_values_and_missing_book_are_handled(client):
    for data, text in ((book_data(release_date="bad-date"), b"valid release date"), (book_data(rating="3.2"), b"half-star increments"), (book_data(format="Kindle"), b"Written or Audible"), (book_data(status="Paused"), b"valid reading status")):
        response = client.post("/reading/new", data=data)
        assert response.status_code == 400 and text in response.data
    assert client.post("/reading/999999").status_code == 404
    assert client.post("/reading/999999/delete").status_code == 404


def test_full_half_ratings_and_interface_assets(client, app):
    client.post("/reading/new", data=book_data(title="Full", rating="5"))
    client.post("/reading/new", data=book_data(title="Half", rating="2.5"))
    page = client.get("/reading/new"); script = client.get("/static/js/reading.js")
    with app.app_context(): assert {book.title: book.rating for book in ReadingItem.query.all()} == {"Full":5.0,"Half":2.5}
    assert b"data-book-stars" in page.data and b"Delete this book permanently?" in script.data
