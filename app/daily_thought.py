"""Offline, deterministic daily micro-lesson selection for the Hub."""
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse


WEEKDAY_CATEGORIES = (
    ("product_strategy", "Monday", "Product / Strategy"),
    ("history", "Tuesday", "History"),
    ("psychology", "Wednesday", "Psychology"),
    ("economics", "Thursday", "Economics"),
    ("science_technology", "Friday", "Science / Technology"),
    ("interesting_fact", "Saturday", "Interesting Fact"),
    ("quote_philosophy", "Sunday", "Quote / Philosophy"),
)
VALID_CATEGORIES = {category for category, _, _ in WEEKDAY_CATEGORIES}
DEFAULT_LIBRARY_PATH = Path(__file__).with_name("data") / "daily_thoughts.json"


@dataclass(frozen=True)
class DailyThought:
    id: str
    category: str
    weekday: str
    category_label: str
    title: str
    what_it_is: str
    why_it_matters: str
    example: str | None
    think_about: str
    attribution: str | None = None
    source_name: str | None = None
    source_url: str | None = None


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value):
    value = _text(value)
    return value or None


def _safe_https_url(value):
    value = _optional_text(value)
    parsed = urlparse(value or "")
    return value if parsed.scheme == "https" and parsed.netloc else None


def load_library(path=DEFAULT_LIBRARY_PATH):
    """Load and validate the curated library; invalid content fails before release."""
    try:
        items = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as error:
        raise ValueError("Daily thought library could not be loaded") from error
    if not isinstance(items, list):
        raise ValueError("Daily thought library must be a list")

    seen_ids, thoughts = set(), []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Daily thought entries must be objects")
        identifier, category = _text(item.get("id")), _text(item.get("category"))
        title, what_it_is, why_it_matters, think_about = (
            _text(item.get(field))
            for field in ("title", "what_it_is", "why_it_matters", "think_about")
        )
        example = _optional_text(item.get("example"))
        if not identifier or identifier in seen_ids or category not in VALID_CATEGORIES:
            raise ValueError("Daily thought id or category is invalid")
        lesson_text = (title, what_it_is, why_it_matters, example or "", think_about)
        if not title or not what_it_is or not why_it_matters or not think_about or any("<" in value for value in lesson_text):
            raise ValueError("Daily thought content is incomplete or contains markup")
        attribution = _optional_text(item.get("attribution"))
        source_name, source_url = _optional_text(item.get("source_name")), _safe_https_url(item.get("source_url"))
        if bool(source_name) != bool(source_url) or not source_url:
            raise ValueError("Daily thought source metadata is invalid")
        seen_ids.add(identifier)
        thoughts.append({
            "id": identifier, "category": category, "title": title,
            "what_it_is": what_it_is, "why_it_matters": why_it_matters,
            "example": example, "think_about": think_about, "attribution": attribution,
            "source_name": source_name, "source_url": source_url,
        })

    counts = {category: sum(item["category"] == category for item in thoughts) for category in VALID_CATEGORIES}
    if any(count < 8 for count in counts.values()):
        raise ValueError("Each daily thought category needs at least eight entries")
    return tuple(thoughts)


def audit_library(path=DEFAULT_LIBRARY_PATH):
    """Return a local-only structural and anti-template audit for release checks."""
    entries = load_library(path)
    by_category = {}
    for category in sorted(VALID_CATEGORIES):
        category_entries = [item for item in entries if item["category"] == category]
        by_category[category] = {
            "total": len(category_entries),
            "sourced": sum(bool(item["source_url"]) for item in category_entries),
            "unsourced": sum(not item["source_url"] for item in category_entries),
        }

    def duplicates(field):
        values = [item[field].casefold().strip() for item in entries]
        return sorted({value for value in values if values.count(value) > 1})

    generic_question_patterns = (
        "what changes in your view", "how does this change the way you think",
        "why does this matter to you", "how might this apply",
    )
    generic_questions = [
        item["id"] for item in entries
        if any(pattern in item["think_about"].casefold() for pattern in generic_question_patterns)
    ]
    titles = [(item["id"], set(item["title"].casefold().replace("/", " ").split())) for item in entries]
    similar_titles = []
    for index, (identifier, words) in enumerate(titles):
        for other_identifier, other_words in titles[index + 1:]:
            if words and other_words and len(words & other_words) / len(words | other_words) >= 0.8:
                similar_titles.append((identifier, other_identifier))
    return {
        "total": len(entries), "categories": by_category, "duplicate_ids": duplicates("id"),
        "duplicate_explanations": duplicates("what_it_is"), "duplicate_questions": duplicates("think_about"),
        "similar_titles": similar_titles, "generic_questions": generic_questions,
    }


class DailyThoughtService:
    def __init__(self, library_path=DEFAULT_LIBRARY_PATH):
        self.library_path = Path(library_path)

    def get_thought(self, selected_date: date):
        if not isinstance(selected_date, date):
            raise ValueError("A calendar date is required")
        category, weekday, category_label = WEEKDAY_CATEGORIES[selected_date.weekday()]
        entries = [item for item in load_library(self.library_path) if item["category"] == category]
        return DailyThought(**entries[(selected_date.toordinal() // 7) % len(entries)], weekday=weekday, category_label=category_label)
