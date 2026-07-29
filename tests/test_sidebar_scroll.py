import pytest

from app.extensions import db
from app.models import GameJournal, Note, ReadingItem, WatchlistItem


@pytest.mark.parametrize(
    ("url", "module_name"),
    [
        ("/notes/", b'data-sidebar-module="notes"'),
        ("/reading/", b'data-sidebar-module="reading"'),
        ("/games/", b'data-sidebar-module="games"'),
        ("/watchlist/", b"watchlist-page"),
    ],
)
def test_sidebar_detail_pages_load_with_scroll_support(client, url, module_name):
    response = client.get(url)
    assert response.status_code == 200
    assert module_name in response.data


def test_selected_sidebar_items_remain_highlighted_and_keyboard_links_work(client, app):
    with app.app_context():
        note = Note(title="Selected note", body="Body")
        book = ReadingItem(title="Selected book", format="Written", status="To Read", notes="")
        game = GameJournal(title="Selected game", status="Backlog", platform="", notes="")
        watch = WatchlistItem(title="Selected watch", media_type="Movie", status="Want to Watch", genre="", recommendation_note="", notes="")
        db.session.add_all([note, book, game, watch])
        db.session.commit()
        identifiers = (note.id, book.id, game.id, watch.id)
    note_page = client.get(f"/notes/?note_id={identifiers[0]}")
    book_page = client.get(f"/reading/?book_id={identifiers[1]}")
    game_page = client.get(f"/games/?game_id={identifiers[2]}")
    watch_page = client.get(f"/watchlist/?item_id={identifiers[3]}")
    for page in (note_page, book_page, game_page, watch_page):
        assert b"active" in page.data and b"aria-current=\"page\"" in page.data


def test_sidebar_scroll_helper_preserves_clamped_module_scoped_positions():
    script = open("app/static/js/sidebar_scroll.js", encoding="utf-8").read()
    assert "sessionStorage" in script
    assert "joshs-corner:sidebar-scroll:${moduleName}" in script
    assert "Math.min(Math.max(0, value)" in script
    assert "data-sidebar-filters" in script
    assert "sidebar-selection" in script
    assert "watchlist-page" in script


def test_sidebar_layout_keeps_independent_desktop_scroll_and_stacks_on_mobile():
    stylesheet = open("app/static/css/sidebar_layout.css", encoding="utf-8").read()
    for selector in (".notes-list", ".book-list", ".watch-list", ".game-list"):
        assert selector in stylesheet
    assert "overflow-y: auto" in stylesheet
    assert "@media (max-width: 700px)" in stylesheet
    assert "overflow: visible" in stylesheet
    assert "height: auto" in stylesheet
