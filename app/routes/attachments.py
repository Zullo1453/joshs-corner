from flask import Blueprint, abort, jsonify, request, send_file

from ..attachments import ImageValidationError, attachment_path, create_draft_attachment, delete_attachment
from ..extensions import db
from ..models import Attachment


attachments_bp = Blueprint("attachments", __name__, url_prefix="/attachments")


@attachments_bp.post("/upload")
def upload():
    image = request.files.get("image")
    if image is None:
        return jsonify(error="Choose an image to upload."), 400
    try:
        attachment = create_draft_attachment(image, request.form.get("draft_token", ""))
    except ImageValidationError as error:
        return jsonify(error=str(error)), 400
    return jsonify(
        id=attachment.id,
        url=f"/attachments/{attachment.id}",
        width=attachment.width,
        height=attachment.height,
        mime_type=attachment.mime_type,
    ), 201


@attachments_bp.get("/<int:attachment_id>")
def serve(attachment_id):
    attachment = db.get_or_404(Attachment, attachment_id)
    path = attachment_path(attachment)
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype=attachment.mime_type, conditional=True, max_age=0)


@attachments_bp.post("/<int:attachment_id>/delete")
def delete(attachment_id):
    attachment = db.get_or_404(Attachment, attachment_id)
    delete_attachment(attachment)
    db.session.commit()
    return ("", 204)
