import re

from app import create_app
from app.extensions import db
from app.models import GameJournal, GamePlayEntry


def add_game(app, title="Game", **values):
    with app.app_context():
        game = GameJournal(title=title, **values)
        db.session.add(game)
        db.session.commit()
        return game.id


def game_data(**overrides):
    values = {
        "title": "Hollow Knight",
        "status": "Playing",
        "rating": "4.5",
        "platform": "Nintendo Switch",
        "hours_played": "18.5",
        "notes": "Exploring the forgotten crossroads.",
    }
    values.update(overrides)
    return values


def test_games_page_loads_with_empty_state(client):
    response = client.get("/games/")

    assert response.status_code == 200
    assert b"New Game Journal" in response.data
    assert b"No game journals yet." in response.data


def test_game_detail_fragment_reuses_the_editor_and_invalid_games_are_safe(client, app):
    first_id = add_game(app, "First game", status="Playing", notes="First notes")
    second_id = add_game(app, "Second game", status="Completed", notes="Second notes")

    full_page = client.get(f"/games/?game_id={second_id}")
    fragment = client.get(f"/games/detail/{second_id}")

    assert full_page.status_code == 200
    assert b"data-game-detail-slot" in full_page.data
    assert b"game-sidebar" in full_page.data
    assert f"/games/?game_id={second_id}".encode() in full_page.data
    assert b"First game" in full_page.data
    assert fragment.status_code == 200
    assert b"data-game-editor" in fragment.data
    assert b'data-game-id="%d"' % second_id in fragment.data
    assert b"Second game" in fragment.data
    assert b"game-sidebar" not in fragment.data
    assert b"<!doctype html>" not in fragment.data.lower()
    assert client.get("/games/detail/999999").status_code == 404


def test_game_partial_save_is_csrf_protected_and_returns_authoritative_sidebar_card(tmp_path):
    database = tmp_path / "games-csrf.db"
    csrf_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}", "WTF_CSRF_ENABLED": True})
    with csrf_app.app_context():
        db.create_all()
    csrf_client = csrf_app.test_client()
    game_id = add_game(csrf_app, "Before fragment save", status="Backlog", notes="Before notes")
    fragment = csrf_client.get(f"/games/detail/{game_id}")
    token = re.search(rb'name="csrf_token" value="([^"]+)"', fragment.data).group(1).decode()

    blocked = csrf_client.post(
        f"/games/{game_id}", data=game_data(title="Blocked"), headers={"X-Requested-With": "JoshCornerPartial"}
    )
    assert blocked.status_code == 400
    saved = csrf_client.post(
        f"/games/{game_id}",
        data={**game_data(title="Saved after fragment selection", status="Completed", notes="Updated notes"), "csrf_token": token, "q": "", "filter_status": "all"},
        headers={"X-Requested-With": "JoshCornerPartial", "X-CSRFToken": token},
    )
    assert saved.status_code == 200 and saved.json["status"] == "saved"
    assert "Saved after fragment selection" in saved.json["sidebar_card_html"]
    assert "Completed" in saved.json["sidebar_card_html"]
    # A second fragment load represents a Back/Forward return to the editor.
    history_fragment = csrf_client.get(f"/games/detail/{game_id}")
    history_token = re.search(rb'name="csrf_token" value="([^"]+)"', history_fragment.data).group(1).decode()
    saved_again = csrf_client.post(
        f"/games/{game_id}",
        data={**game_data(title="Saved after history navigation", notes="History notes"), "csrf_token": history_token, "q": "", "filter_status": "all"},
        headers={"X-Requested-With": "JoshCornerPartial", "X-CSRFToken": history_token},
    )
    assert saved_again.status_code == 200 and saved_again.json["game_id"] == game_id
    with csrf_app.app_context():
        assert db.session.get(GameJournal, game_id).notes == "History notes"


def test_failed_partial_game_save_returns_json_without_changing_the_saved_game(client, app):
    game_id = add_game(app, "Saved title", status="Backlog", notes="Saved notes")
    response = client.post(
        f"/games/{game_id}",
        data={**game_data(title="   ", notes="Draft that must stay in the browser"), "q": "", "filter_status": "all"},
        headers={"X-Requested-With": "JoshCornerPartial"},
    )

    assert response.status_code == 400
    assert response.json == {"status": "error", "error": "A game title is required."}
    with app.app_context():
        game = db.session.get(GameJournal, game_id)
        assert game.title == "Saved title"
        assert game.notes == "Saved notes"


def test_game_discrete_autosave_uses_only_the_explicit_payload_and_updates_its_card(client, app):
    game_id = add_game(app, "Saved title", status="Backlog", notes="Saved notes")
    response = client.post(
        f"/games/{game_id}/autosave",
        json={**game_data(title="Saved title", status="Playing", platform="PC", hours_played="12" , notes="Saved notes"), "q": "", "filter_status": "all"},
    )

    assert response.status_code == 200
    assert response.json["game_id"] == game_id
    assert "Playing" in response.json["sidebar_card_html"]
    with app.app_context():
        game = db.session.get(GameJournal, game_id)
        assert game.title == "Saved title"
        assert game.notes == "Saved notes"
        assert game.platform == "PC"


def test_game_partial_navigation_client_is_scoped_and_preserves_hybrid_save_behaviour():
    script = open("app/static/js/games.js", encoding="utf-8").read()
    detail_template = open("app/templates/games/_detail.html", encoding="utf-8").read()

    assert "[data-sidebar-module='games']" in script
    assert "data-game-detail-slot" in script
    assert "fetch(partial" in script
    assert "history.pushState" in script and '"popstate"' in script
    assert "slot.innerHTML" in script and "setSelectedGame" in script
    assert "You have unsaved changes. Leave without saving?" in script
    assert "event.metaKey" in script and "event.ctrlKey" in script and "event.shiftKey" in script and "event.altKey" in script
    assert 'link.hasAttribute("download")' in script and "!link.target" in script
    assert "scrollIntoView" not in script
    assert "game-navigation-error" in script and "Open normally" in script
    assert "gameSnapshot" in script and "title: gameSnapshot.title" in script
    assert 'fetch(form.getAttribute("action")' in script
    assert "fetch(form.action" not in script
    assert "JoshsCornerAutosave?.initialise" not in script
    assert "data-add-play-entry" in script and "data-play-entry-editor" in script
    assert "destroyGameDetail" in script and "JoshsCornerRichText?.destroy(slot)" in script
    assert 'name="csrf_token" value="{{ csrf_token() }}"' in detail_template
    assert "data-game-card-id" in open("app/templates/games/_sidebar_card.html", encoding="utf-8").read()


def test_create_game_journal(client, app):
    response = client.post("/games/new", data=game_data(), follow_redirects=True)

    assert response.status_code == 200
    assert b"Hollow Knight" in response.data
    with app.app_context():
        game = GameJournal.query.one()
        assert game.status == "Playing"
        assert game.rating == 4.5
        assert game.platform == "Nintendo Switch"
        assert game.hours_played == 18.5


def test_blank_title_is_rejected(client, app):
    response = client.post("/games/new", data=game_data(title="   "))

    assert response.status_code == 400
    assert b"A game title is required." in response.data
    with app.app_context():
        assert GameJournal.query.count() == 0


def test_update_game_journal(client, app):
    game_id = add_game(app, "Before", status="Backlog", notes="Old note")

    response = client.post(
        f"/games/{game_id}", data=game_data(title="After", status="Completed", notes="New note"), follow_redirects=True
    )

    assert response.status_code == 200
    assert b"After" in response.data
    with app.app_context():
        game = db.session.get(GameJournal, game_id)
        assert game.status == "Completed"
        assert game.notes == "New note"


def test_existing_game_and_play_entry_autosave(client, app):
    game_id = add_game(app, "Before", status="Backlog", notes="Old")
    game_response = client.post(f"/games/{game_id}/autosave", json=game_data(title="After", notes="<p>Review<script>x</script></p>"))
    client.post(f"/games/{game_id}/play-log", data={"played_on": "2026-07-20", "title": "First", "body": "Before"})
    with app.app_context(): entry_id = GamePlayEntry.query.one().id
    play_response = client.post(f"/games/{game_id}/play-log/{entry_id}/autosave", json={"played_on": "2026-07-21", "title": "Updated", "body": "<p>After</p>"})
    assert game_response.status_code == 200 and play_response.status_code == 200
    with app.app_context():
        assert db.session.get(GameJournal, game_id).title == "After"
        assert db.session.get(GamePlayEntry, entry_id).title == "Updated"
        assert GamePlayEntry.query.count() == 1


def test_delete_game_journal(client, app):
    game_id = add_game(app, "Temporary")

    response = client.post(f"/games/{game_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert b"No game journals yet." in response.data
    with app.app_context():
        assert db.session.get(GameJournal, game_id) is None


def test_search_by_title_and_notes(client, app):
    add_game(app, "Outer Wilds", notes="Ancient Nomai messages")
    add_game(app, "Celeste", notes="Mountain climbing")

    title_response = client.get("/games/?q=outer")
    notes_response = client.get("/games/?q=nomai")

    assert b"Outer Wilds" in title_response.data and b"Celeste" not in title_response.data
    assert b"Outer Wilds" in notes_response.data and b"Celeste" not in notes_response.data


def test_status_and_combined_filters(client, app):
    add_game(app, "Active Quest", status="Playing", notes="Forest map")
    add_game(app, "Old Quest", status="Completed", notes="Forest map")
    add_game(app, "Other Quest", status="Playing", notes="Desert map")

    filtered = client.get("/games/?status=Playing")
    combined = client.get("/games/?status=Playing&q=forest")

    assert b"Active Quest" in filtered.data and b"Old Quest" not in filtered.data
    assert b"Active Quest" in combined.data
    assert b"Old Quest" not in combined.data and b"Other Quest" not in combined.data


def test_platform_and_blank_or_valid_hours_played(client, app):
    response = client.post("/games/new", data=game_data(hours_played="", platform="PC"), follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        game = GameJournal.query.one()
        assert game.platform == "PC"
        assert game.hours_played is None

    response = client.post(f"/games/{game.id}", data=game_data(hours_played="123.25"), follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(GameJournal, game.id).hours_played == 123.25


def test_negative_and_excessive_hours_are_rejected(client, app):
    for hours in ("-1", "100000.5"):
        response = client.post("/games/new", data=game_data(hours_played=hours))
        assert response.status_code == 400
        assert b"Hours played must be between 0 and 100000." in response.data
    with app.app_context():
        assert GameJournal.query.count() == 0


def test_full_and_half_star_ratings_are_saved(client, app):
    full = client.post("/games/new", data=game_data(title="Full", rating="5"), follow_redirects=True)
    half = client.post("/games/new", data=game_data(title="Half", rating="3.5"), follow_redirects=True)

    assert b"5.0 / 5" in full.data
    assert b"3.5 / 5" in half.data
    with app.app_context():
        ratings = {game.title: game.rating for game in GameJournal.query.all()}
        assert ratings == {"Full": 5.0, "Half": 3.5}


def test_invalid_rating_status_and_missing_id_are_handled(client, app):
    invalid_rating = client.post("/games/new", data=game_data(rating="3.2"))
    invalid_status = client.post("/games/new", data=game_data(status="Unknown"))

    assert invalid_rating.status_code == 400
    assert b"half-star increments" in invalid_rating.data
    assert invalid_status.status_code == 400
    assert b"valid game status" in invalid_status.data
    assert client.post("/games/999999/delete").status_code == 404
    assert client.post("/games/999999").status_code == 404


def test_game_controls_and_delete_confirmation_assets(client):
    page = client.get("/games/new")
    script = client.get("/static/js/games.js")

    assert b'data-rating-stars' in page.data
    assert b'data-star="1"' in page.data
    assert b"Delete this game journal permanently?" in script.data


def test_writing_area_uses_a_spaced_line_grid_for_readability(client):
    stylesheet = client.get("/static/css/games.css")

    assert b"background-size:100% 34px" in stylesheet.data
    assert b"background-position:0 9px" in stylesheet.data
    assert b"font:1rem/34px" in stylesheet.data


def test_game_sidebar_scrollbar_is_scoped_to_the_game_theme(client):
    stylesheet = open("app/static/css/games_partial_navigation.css", encoding="utf-8").read()

    assert ".games-page .game-list" in stylesheet
    assert "scrollbar-color:var(--gold) var(--panel)" in stylesheet
    assert ".games-page .game-list::-webkit-scrollbar" in stylesheet
    assert "::-webkit-scrollbar-track" in stylesheet
    assert "::-webkit-scrollbar-thumb:hover" in stylesheet
    assert ".watch-list" not in stylesheet and ".book-list" not in stylesheet and ".notes-list" not in stylesheet


def test_play_entries_are_independent_and_ordered(client, app):
    game_id = add_game(app, "Logbook", notes="Overall review stays here")
    first = client.post(f"/games/{game_id}/play-log", data={"played_on": "2026-07-20", "title": "First", "body": "A safe first session."})
    second = client.post(f"/games/{game_id}/play-log", data={"played_on": "2026-07-21", "title": "Second", "body": "A newer session."})
    assert first.status_code == 302 and second.status_code == 302
    page = client.get(f"/games/?game_id={game_id}")
    assert page.data.index(b"Second") < page.data.index(b"First")
    with app.app_context():
        assert GameJournal.query.get(game_id).notes == "Overall review stays here"
        assert GamePlayEntry.query.count() == 2
        entry = GamePlayEntry.query.first()
        client.post(f"/games/{game_id}/play-log/{entry.id}/delete")
        assert db.session.get(GameJournal, game_id) is not None


def test_play_entry_requires_date_and_body_and_handles_missing_game(client, app):
    assert client.post("/games/999/play-log", data={}).status_code == 404
    game_id = add_game(app)
    bad = client.post(f"/games/{game_id}/play-log", data={"played_on": "", "body": ""})
    assert bad.status_code == 400
    assert b"valid date" in bad.data


def test_save_journal_keeps_or_saves_the_current_play_draft(client, app):
    game_id = add_game(app, "Draft guard", notes="Before")
    valid = game_data(title="Draft guard", notes="After")
    valid.update({"played_on": "2026-07-28", "play_title": "A session", "play_body": "A complete play note."})
    response = client.post(f"/games/{game_id}", data=valid)
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(GameJournal, game_id).notes == "After"
        assert GamePlayEntry.query.count() == 1

    partial = game_data(title="Draft guard", notes="Saved overall")
    partial.update({"played_on": "", "play_title": "Keep this", "play_body": ""})
    response = client.post(f"/games/{game_id}", data=partial)
    assert response.status_code == 400
    assert b"draft has not been cleared" in response.data
    assert b"Keep this" in response.data
    with app.app_context():
        assert db.session.get(GameJournal, game_id).notes == "Saved overall"
        assert GamePlayEntry.query.count() == 1
