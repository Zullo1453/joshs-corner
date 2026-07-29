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
    assert rich_text_preview(value) == "One & two three four"
    assert rich_text_preview("<p><br></p>") == ""
    assert rich_text_preview("<script>alert(1)</script><p>safe words here</p>", 10) == "alert(1)…"
    assert "<" not in rich_text_preview(value)


def test_local_image_sanitisation_allows_only_attachment_routes():
    assert sanitise_rich_text_html('<img src="/attachments/3" alt="okay" onclick="bad()">') == '<img src="/attachments/3" alt="okay">'
    assert sanitise_rich_text_html('<img src="https://example.com/a.png"><img src="data:image/png;base64,x">') == ""


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
