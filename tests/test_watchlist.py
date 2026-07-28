from app.extensions import db
from app.models import WatchlistItem


def add_item(app, title="Item", **values):
    with app.app_context():
        item = WatchlistItem(title=title, **values)
        db.session.add(item)
        db.session.commit()
        return item.id


def item_data(**overrides):
    values = {"title": "Arrival", "media_type": "Movie", "status": "Finished", "rating": "4.5", "release_year": "2016", "genre": "Sci-Fi", "recommendation_note": "Recommended by Sam", "notes": "A thoughtful first-contact story."}
    values.update(overrides)
    return values


def test_watchlist_loads_with_empty_state(client):
    response = client.get("/watchlist/")
    assert response.status_code == 200
    assert b"Add to Watchlist" in response.data
    assert b"Your watchlist is empty." in response.data


def test_create_movie_and_show(client, app):
    movie = client.post("/watchlist/new", data=item_data(), follow_redirects=True)
    show = client.post("/watchlist/new", data=item_data(title="Severance", media_type="Show", status="Watching"), follow_redirects=True)
    assert b"Arrival" in movie.data and b"Severance" in show.data
    with app.app_context():
        assert {item.media_type for item in WatchlistItem.query.all()} == {"Movie", "Show"}


def test_blank_title_update_and_delete(client, app):
    blank = client.post("/watchlist/new", data=item_data(title="  "))
    assert blank.status_code == 400 and b"A title is required." in blank.data
    item_id = add_item(app, "Before", media_type="Movie", status="Want to Watch")
    updated = client.post(f"/watchlist/{item_id}", data=item_data(title="After", notes="Updated"), follow_redirects=True)
    assert b"After" in updated.data
    deleted = client.post(f"/watchlist/{item_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200
    with app.app_context(): assert db.session.get(WatchlistItem, item_id) is None


def test_searches_and_combined_filters(client, app):
    add_item(app, "Severance", media_type="Show", status="Watching", genre="Sci-Fi", recommendation_note="Office recommendation", notes="Strange workplace drama")
    add_item(app, "Arrival", media_type="Movie", status="Finished", genre="Drama", recommendation_note="Aliens recommendation", notes="Quiet review")
    assert b"Severance" in client.get("/watchlist/?q=severance").data
    assert b"Severance" in client.get("/watchlist/?q=office").data
    assert b"Severance" in client.get("/watchlist/?q=workplace").data
    combined = client.get("/watchlist/?q=office&type=Show&status=Watching&genre=Sci-Fi")
    assert b"Severance" in combined.data and b"Arrival" not in combined.data
    assert b"Arrival" not in client.get("/watchlist/?type=Show").data
    assert b"Severance" not in client.get("/watchlist/?status=Finished").data
    assert b"Arrival" in client.get("/watchlist/?genre=Drama").data


def test_optional_and_valid_release_year(client, app):
    client.post("/watchlist/new", data=item_data(title="No year", release_year=""))
    client.post("/watchlist/new", data=item_data(title="Old film", release_year="1888"))
    with app.app_context():
        values = {item.title: item.release_year for item in WatchlistItem.query.all()}
        assert values == {"No year": None, "Old film": 1888}


def test_invalid_year_rating_type_status_and_missing_id(client):
    for data, message in ((item_data(release_year="1800"), b"Release year"), (item_data(rating="3.2"), b"half-star increments"), (item_data(media_type="Book"), b"Movie or Show"), (item_data(status="Paused"), b"valid watch status")):
        response = client.post("/watchlist/new", data=data)
        assert response.status_code == 400 and message in response.data
    assert client.post("/watchlist/999999").status_code == 404
    assert client.post("/watchlist/999999/delete").status_code == 404


def test_full_and_half_star_ratings_and_assets(client, app):
    client.post("/watchlist/new", data=item_data(title="Full", rating="5"))
    client.post("/watchlist/new", data=item_data(title="Half", rating="2.5"))
    page = client.get("/watchlist/new"); stylesheet = client.get("/static/css/watchlist.css"); script = client.get("/static/js/watchlist.js")
    with app.app_context(): assert {item.title: item.rating for item in WatchlistItem.query.all()} == {"Full": 5.0, "Half": 2.5}
    assert b"perspective(380px) rotateX(64deg)" in stylesheet.data
    assert b"data-watch-stars" in page.data
    assert b"Delete this watchlist item permanently?" in script.data
