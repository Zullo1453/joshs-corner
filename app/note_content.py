from html import escape
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
    "i",
    "li",
    "ol",
    "p",
    "strong",
    "u",
    "ul",
}
VOID_TAGS = {"br"}


class SafeNoteHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag in ALLOWED_TAGS:
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
