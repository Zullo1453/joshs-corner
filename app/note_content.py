from html import escape, unescape
from html.parser import HTMLParser
import re


ALLOWED_TAGS = {
    "b",
    "blockquote",
    "br",
    "div",
    "em",
    "h1",
    "h2",
    "img",
    "i",
    "li",
    "ol",
    "p",
    "strong",
    "u",
    "ul",
}
VOID_TAGS = {"br", "img"}
LOCAL_ATTACHMENT_RE = re.compile(r"^/attachments/(\d+)$")
BLOCK_TAGS = {"blockquote", "div", "h1", "h2", "li", "ol", "p", "ul"}
IMAGE_FORMAT_CLASSES = {
    "image-size-small",
    "image-size-medium",
    "image-size-large",
    "image-size-full",
    "image-align-left",
    "image-align-center",
    "image-align-right",
}


class SafeNoteHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            attributes = dict(attrs)
            source = attributes.get("src", "")
            if not LOCAL_ATTACHMENT_RE.fullmatch(source):
                return
            safe = [f'src="{escape(source, quote=True)}"']
            alt = attributes.get("alt", "")
            if alt:
                safe.append(f'alt="{escape(alt[:200], quote=True)}"')
            for dimension in ("width", "height"):
                value = attributes.get(dimension, "")
                if value.isdigit() and 1 <= int(value) <= 2560:
                    safe.append(f'{dimension}="{int(value)}"')
            classes = [name for name in attributes.get("class", "").split() if name in IMAGE_FORMAT_CLASSES]
            if classes:
                safe.append(f'class="{" ".join(classes)}"')
            self.parts.append("<img " + " ".join(safe) + ">")
        elif tag in ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag == "img":
            self.handle_starttag(tag, attrs)
        elif tag in ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(escape(data))


def sanitise_rich_text_html(value):
    parser = SafeNoteHTMLParser()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.parts)


def sanitise_note_html(value):
    """Compatibility name retained for the General Notes routes."""
    return sanitise_rich_text_html(value)


def is_visually_empty_html(value):
    """Treat editor scaffolding such as <p><br></p> as empty content."""
    return not re.sub(r"<[^>]+>", "", sanitise_rich_text_html(value)).replace("&nbsp;", " ").strip()


class _PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)


def rich_text_preview(value, limit=92):
    """Return a readable, plain-text excerpt without rendering stored markup."""
    parser = _PreviewParser()
    parser.feed(sanitise_rich_text_html(value or ""))
    parser.close()
    text = " ".join(unescape("".join(parser.parts)).split())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    clipped = text[: max(1, limit - 1)].rsplit(" ", 1)[0].rstrip()
    return (clipped or text[: max(1, limit - 1)]).rstrip(" .,;:") + "…"
