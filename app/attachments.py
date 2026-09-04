"""Local-only image attachment storage and association helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import re
import secrets

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from .extensions import db
from .models import Attachment


MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_EDGE = 2560
OWNER_TYPES = {"journal", "note", "game", "game_play", "reading", "watchlist"}
ATTACHMENT_SRC_RE = re.compile(r'<img\b[^>]*\bsrc=["\']/attachments/(\d+)["\']', re.I)


class ImageValidationError(ValueError):
    """The submitted upload is not a supported safe image."""


def configured_upload_root(app=None) -> Path:
    app = app or current_app
    configured = app.config.get("UPLOAD_ROOT")
    return Path(configured) if configured else Path(app.instance_path) / "uploads"


def upload_root() -> Path:
    root = configured_upload_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def attachment_path(attachment: Attachment) -> Path:
    # stored_filename is generated below; name-only resolution prevents traversal.
    return upload_root() / Path(attachment.stored_filename).name


def _process_image(raw: bytes) -> tuple[bytes, str, str, int, int]:
    if not raw:
        raise ImageValidationError("Choose an image to upload.")
    if len(raw) > MAX_INPUT_BYTES:
        raise ImageValidationError("Images must be 10 MB or smaller.")
    try:
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as opened:
            source_format = opened.format
            image = ImageOps.exif_transpose(opened)
            image.load()
            if source_format not in {"PNG", "JPEG", "WEBP"}:
                raise ImageValidationError("Only PNG, JPEG, and WebP images are supported.")
            if image.width < 1 or image.height < 1:
                raise ImageValidationError("This image has invalid dimensions.")
            if max(image.size) > MAX_EDGE:
                image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            has_alpha = "A" in image.getbands() or image.mode == "P" and "transparency" in image.info
            output = BytesIO()
            if has_alpha:
                image.convert("RGBA").save(output, format="PNG", optimize=True)
                return output.getvalue(), "image/png", "png", image.width, image.height
            image.convert("RGB").save(output, format="WEBP", quality=88, method=6)
            return output.getvalue(), "image/webp", "webp", image.width, image.height
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ImageValidationError("The uploaded file is not a valid PNG, JPEG, or WebP image.") from error


def create_draft_attachment(file_storage, draft_token: str) -> Attachment:
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,64}", draft_token or ""):
        raise ImageValidationError("The editor upload token is invalid. Refresh the page and try again.")
    raw = file_storage.read(MAX_INPUT_BYTES + 1)
    data, mime_type, extension, width, height = _process_image(raw)
    filename = f"{secrets.token_urlsafe(24)}.{extension}"
    attachment = Attachment(
        owner_type="draft",
        owner_id=None,
        draft_token=draft_token,
        stored_filename=filename,
        original_filename=Path(file_storage.filename or "image").name[:255] or "image",
        mime_type=mime_type,
        file_size=len(data),
        width=width,
        height=height,
    )
    path = attachment_path(attachment)
    try:
        path.write_bytes(data)
        db.session.add(attachment)
        db.session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        db.session.rollback()
        raise
    return attachment


def local_attachment_ids(html: str) -> set[int]:
    return {int(value) for value in ATTACHMENT_SRC_RE.findall(html or "")}


def delete_attachment(attachment: Attachment) -> None:
    path = attachment_path(attachment)
    db.session.delete(attachment)
    db.session.flush()
    path.unlink(missing_ok=True)


def sync_attachments(html: str, owner_type: str, owner_id: int, draft_token: str | None = None) -> None:
    """Make a record's attachment set exactly match its sanitised rich HTML."""
    if owner_type not in OWNER_TYPES:
        raise ValueError("Unknown attachment owner type")
    wanted = local_attachment_ids(html)
    linked = list(
        db.session.execute(
            db.select(Attachment).where(
                Attachment.owner_type == owner_type,
                Attachment.owner_id == owner_id,
            )
        ).scalars()
    )
    for attachment in linked:
        if attachment.id not in wanted:
            delete_attachment(attachment)
    if wanted:
        candidates = db.session.execute(
            db.select(Attachment).where(Attachment.id.in_(wanted))
        ).scalars().all()
        for attachment in candidates:
            is_linked = attachment.owner_type == owner_type and attachment.owner_id == owner_id
            is_matching_draft = attachment.owner_type == "draft" and draft_token and attachment.draft_token == draft_token
            if is_linked or is_matching_draft:
                attachment.owner_type = owner_type
                attachment.owner_id = owner_id
                attachment.draft_token = None


def delete_owner_attachments(owner_type: str, owner_id: int) -> None:
    attachments = db.session.execute(
        db.select(Attachment).where(
            Attachment.owner_type == owner_type,
            Attachment.owner_id == owner_id,
        )
    ).scalars().all()
    for attachment in attachments:
        delete_attachment(attachment)


def attachment_diagnostics(candidate_age_days: int = 30) -> dict:
    root = upload_root()
    records = db.session.execute(db.select(Attachment)).scalars().all()
    record_names = {attachment.stored_filename for attachment in records}
    files = [path for path in root.iterdir() if path.is_file()]
    cutoff = datetime.now(timezone.utc) - timedelta(days=candidate_age_days)
    missing = [attachment.id for attachment in records if not attachment_path(attachment).is_file()]
    candidates = [
        path.name for path in files
        if path.name not in record_names and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff
    ]
    return {
        "stored_images": len(records),
        "total_bytes": sum(attachment.file_size for attachment in records),
        "upload_directory": str(root),
        "missing_attachment_ids": missing,
        "unreferenced_file_candidates": candidates,
    }
