from app.extensions import db
from app.models import Note


def add_note(app, title, body, favourite=False):
    with app.app_context():
        note = Note(title=title, body=body, is_favourite=favourite)
        db.session.add(note)
        db.session.commit()
        return note.id


def test_notes_page_loads_with_empty_state(client):
    response = client.get("/notes/")

    assert response.status_code == 200
    assert b"New Note" in response.data
    assert b"No notes yet." in response.data
    assert b"Create your first note" in response.data


def test_create_note(client, app):
    response = client.post(
        "/notes/new",
        data={"title": "First note", "body": "<p>Useful body</p>"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"First note" in response.data
    assert b"Useful body" in response.data
    with app.app_context():
        note = Note.query.one()
        assert note.title == "First note"
        assert note.body == "<p>Useful body</p>"
        assert note.created_at is not None
        assert note.updated_at is not None


def test_update_note(client, app):
    note_id = add_note(app, "Old title", "Old body")

    response = client.post(
        f"/notes/{note_id}",
        data={"title": "Updated title", "body": "<h2>Updated body</h2>"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Updated title" in response.data
    assert b"Updated body" in response.data
    with app.app_context():
        note = db.session.get(Note, note_id)
        assert note.title == "Updated title"
        assert note.body == "<h2>Updated body</h2>"


def test_existing_note_autosaves_without_touching_another_note(client, app):
    note_id = add_note(app, "Before", "Old")
    other_id = add_note(app, "Other", "Unchanged")
    response = client.post(f"/notes/{note_id}/autosave", json={"title": "After", "body": "<p>Safe<script>x</script></p>"})
    assert response.status_code == 200 and response.json["status"] == "saved"
    with app.app_context():
        assert db.session.get(Note, note_id).title == "After"
        assert "script" not in db.session.get(Note, note_id).body
        assert db.session.get(Note, other_id).body == "Unchanged"


def test_delete_note(client, app):
    note_id = add_note(app, "Temporary", "Delete this")

    response = client.post(f"/notes/{note_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert b"No notes yet." in response.data
    with app.app_context():
        assert db.session.get(Note, note_id) is None


def test_search_by_title(client, app):
    add_note(app, "History research", "Roman roads")
    add_note(app, "House ideas", "Warm paint")

    response = client.get("/notes/?q=history")

    assert b"History research" in response.data
    assert b"House ideas" not in response.data


def test_search_by_body_content(client, app):
    add_note(app, "Research", "<p>Read about SQLite backups</p>")
    add_note(app, "Shopping", "<p>Buy coffee</p>")

    response = client.get("/notes/?q=sqlite")

    assert b"Research" in response.data
    assert b"Shopping" not in response.data


def test_favourite_and_unfavourite_note(client, app):
    note_id = add_note(app, "Star me", "Body")

    first_response = client.post(f"/notes/{note_id}/favourite", follow_redirects=True)
    assert first_response.status_code == 200
    with app.app_context():
        assert db.session.get(Note, note_id).is_favourite is True

    second_response = client.post(f"/notes/{note_id}/favourite", follow_redirects=True)
    assert second_response.status_code == 200
    with app.app_context():
        assert db.session.get(Note, note_id).is_favourite is False


def test_favourite_only_filter(client, app):
    add_note(app, "Favourite note", "Keep this", favourite=True)
    add_note(app, "Ordinary note", "Hide this")

    response = client.get("/notes/?favourites=1")

    assert b"Favourite note" in response.data
    assert b"Ordinary note" not in response.data
    assert b'aria-pressed="true"' in response.data


def test_combined_search_and_favourite_filter(client, app):
    add_note(app, "Garden plans", "Native plants", favourite=True)
    add_note(app, "Garden shopping", "Buy a hose")
    add_note(app, "Book notes", "A history chapter", favourite=True)

    response = client.get("/notes/?q=garden&favourites=1")

    assert b"Garden plans" in response.data
    assert b"Garden shopping" not in response.data
    assert b"Book notes" not in response.data


def test_filtered_empty_state(client, app):
    add_note(app, "Only note", "Some content")

    response = client.get("/notes/?q=missing")

    assert b"No notes match these filters." in response.data
    assert b"Clear filters" in response.data


def test_search_form_preserves_favourite_filter(client, app):
    add_note(app, "Favourite note", "Body", favourite=True)

    response = client.get("/notes/?favourites=1")

    search_form = response.data.split(b'data-search-form', 1)[1].split(b"</form>", 1)[0]
    assert b'name="favourites" value="1"' in search_form


def test_rich_text_is_limited_to_safe_supported_markup(client, app):
    response = client.post(
        "/notes/new",
        data={
            "title": "Safe note",
            "body": '<h1>Heading</h1><script>alert("x")</script><a href="https://example.com">link</a>',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        body = Note.query.one().body
        assert body == "<h1>Heading</h1>alert(&quot;x&quot;)link"
        assert "<script" not in body
        assert "<a " not in body


def test_quote_markup_is_preserved_but_can_be_removed_without_losing_text(client, app):
    response = client.post(
        "/notes/new",
        data={
            "title": "Quote toggle",
            "body": '<blockquote onclick="bad()">Quoted text</blockquote><p>Normal text</p><a href="bad">link</a>',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        note = Note.query.one()
        assert note.body == "<blockquote>Quoted text</blockquote><p>Normal text</p>link"
        assert "Quoted text" in note.body.replace("<blockquote>", "<p>").replace("</blockquote>", "</p>")
        assert "onclick" not in note.body and "<a " not in note.body


def test_note_cards_do_not_nest_interactive_controls(client, app):
    note_id = add_note(app, "Valid card", "Body")

    response = client.get(f"/notes/?note_id={note_id}")
    card = response.data.split(f'data-note-id="{note_id}"'.encode(), 1)[1].split(b"</article>", 1)[0]

    link_end = card.index(b"</a>")
    assert b"<button" not in card[:link_end]
    assert b"<form" in card[link_end:]
    assert b"<button" in card[link_end:]


def test_delete_confirmation_and_toolbar_assets_load(client, app):
    note_id = add_note(app, "Editable", "Body")

    page = client.get(f"/notes/?note_id={note_id}")
    script = client.get("/static/js/notes.js")

    assert b'data-command="bold"' in page.data
    assert b'data-command="insertUnorderedList"' in page.data
    assert b"Delete this note? This cannot be undone." in script.data
    assert b'data-quote-toggle' in page.data
    assert b'quoteIsActive() ? "p" : "blockquote"' in script.data


def test_selected_note_renders_one_detail_editor_in_reachable_document_flow(client, app):
    note_id = add_note(app, "Long note", "<p>Paragraph</p>" * 500)

    response = client.get(f"/notes/?note_id={note_id}")

    assert response.status_code == 200
    assert response.data.count(b'class="notes-editor"') == 1
    assert response.data.count(b'data-sidebar-detail-focus') == 1
    assert b"<p>Paragraph</p>" * 500 in response.data
