from io import BytesIO

from PIL import Image

from app.attachments import attachment_path
from app.extensions import db
from app.models import Attachment, Note
from app.note_content import rich_text_preview, sanitise_rich_text_html


def image_bytes(mode="RGB", fmt="PNG"):
    image = Image.new(mode, (40, 30), (30, 80, 150, 120) if "A" in mode else (30, 80, 150))
    output = BytesIO(); image.save(output, fmt); output.seek(0)
    return output


def test_rich_preview_is_plain_readable_and_cleanly_truncated():
    value = "<p><strong>One</strong> &amp; two</p><blockquote>three</blockquote><ul><li>four</li></ul>"
    assert rich_text_preview(value) == "One & two\nthree\nfour"
    assert rich_text_preview("<p><br></p>") == ""
    assert rich_text_preview("<script>alert(1)</script><p>safe words here</p>", 10) == "alert(1)…"
    assert "<" not in rich_text_preview(value)


def test_rich_preview_preserves_safe_line_breaks_without_excessive_blank_space():
    assert rich_text_preview("First<br>Second<br>Third") == "First\nSecond\nThird"
    assert rich_text_preview("<p>First</p><p>Second</p>") == "First\nSecond"
    assert rich_text_preview("First<br><br><br><br>Second") == "First\n\nSecond"


def test_local_image_sanitisation_allows_only_attachment_routes():
    assert sanitise_rich_text_html('<img src="/attachments/3" alt="okay" onclick="bad()">') == '<img src="/attachments/3" alt="okay">'
    assert sanitise_rich_text_html('<img src="https://example.com/a.png"><img src="data:image/png;base64,x">') == ""


def test_image_formatting_sanitisation_keeps_only_trusted_classes():
    value = ('<img src="/attachments/3" class="image-size-large image-align-right injected" '
             'style="width:999px" onclick="bad()" alt="okay">')

    assert sanitise_rich_text_html(value) == ('<img src="/attachments/3" alt="okay" '
                                               'class="image-size-large image-align-right">')
    assert sanitise_rich_text_html('<img src="/attachments/3" class="unknown another" style="width:1px">') == '<img src="/attachments/3">'


def test_shared_rich_text_editor_exposes_controlled_image_formatting_for_every_supported_module():
    editor = open("app/templates/_rich_text_editor.html", encoding="utf-8").read()
    script = open("app/static/js/rich_text.js", encoding="utf-8").read()
    stylesheet = open("app/static/css/rich_text.css", encoding="utf-8").read()
    shared_editor_templates = (
        "app/templates/notes/_detail.html",
        "app/templates/journal/entry.html",
        "app/templates/games/_detail.html",
    )
    converted_textarea_templates = (
        "app/templates/reading/_detail.html",
        "app/templates/watchlist/_detail.html",
    )

    for value in ("small", "medium", "large", "full"):
        assert f'data-rich-image-size="{value}"' in editor
        assert f'"image-size-{value}"' in script
    for value in ("left", "center", "right"):
        assert f'data-rich-image-align="{value}"' in editor
        assert f'"image-align-{value}"' in script
    assert 'image.className = "image-size-medium image-align-center"' in script
    assert "formatSelectedImage" in script
    assert "body.dispatchEvent(new Event(\"input\", {bubbles: true}))" in script
    assert ".rich-editor-body img.image-size-full{width:100%}" in stylesheet
    assert "max-width:100%;height:auto" in stylesheet
    for template in shared_editor_templates:
        assert "_rich_text_editor.html" in open(template, encoding="utf-8").read()
    for template in converted_textarea_templates:
        assert 'textarea' in open(template, encoding="utf-8").read()
    assert "scope.querySelectorAll('textarea[name=\"notes\"]')" in script


def test_upload_associate_and_parent_delete(client, app, tmp_path):
    app.config["UPLOAD_ROOT"] = str(tmp_path / "uploads")
    response = client.post("/attachments/upload", data={"draft_token": "a" * 32, "image": (image_bytes(), "photo.png")}, content_type="multipart/form-data")
    assert response.status_code == 201
    payload = response.get_json(); attachment_id = payload["id"]
    body = f'<p>Hello <img src="{payload["url"]}"></p>'
    saved = client.post("/notes/new", data={"title": "Picture", "body": body, "body_attachment_token": "a" * 32})
    assert saved.status_code == 302
    with app.app_context():
        note = Note.query.one(); attachment = db.session.get(Attachment, attachment_id)
        assert attachment.owner_type == "note" and attachment.owner_id == note.id
        path = attachment_path(attachment); assert path.is_file()
        deleted = client.post(f"/notes/{note.id}/delete")
        assert deleted.status_code == 302 and db.session.get(Attachment, attachment_id) is None and not path.exists()


def test_rejects_malformed_or_fake_image(client, app, tmp_path):
    app.config["UPLOAD_ROOT"] = str(tmp_path / "uploads")
    response = client.post("/attachments/upload", data={"draft_token": "b" * 32, "image": (BytesIO(b"not a picture"), "fake.png")}, content_type="multipart/form-data")
    assert response.status_code == 400
