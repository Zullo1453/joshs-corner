from collections import Counter
from datetime import date
import json

import pytest

from app.daily_thought import DailyThought, DailyThoughtService, VALID_CATEGORIES, WEEKDAY_CATEGORIES, audit_library, load_library
from app.extensions import db
from app.models import CurrencyPair, WeatherLocation
from app.routes import home


def test_curated_library_has_eight_valid_micro_lessons_in_each_weekday_category():
    entries = load_library()
    assert len(entries) == 56
    assert set(item["category"] for item in entries) == VALID_CATEGORIES
    assert Counter(item["category"] for item in entries) == {category: 8 for category in VALID_CATEGORIES}
    assert len({item["id"] for item in entries}) == len(entries)
    for item in entries:
        assert all(item[field] for field in ("id", "category", "title", "what_it_is", "why_it_matters", "think_about"))
        assert all("<" not in item[field] for field in ("what_it_is", "why_it_matters", "think_about"))
        if item["source_url"]:
            assert item["source_url"].startswith("https://") and item["source_name"]


@pytest.mark.parametrize("selected_date, expected", [
    (date(2026, 8, 17), ("product_strategy", "Monday", "Product / Strategy")),
    (date(2026, 8, 18), ("history", "Tuesday", "History")),
    (date(2026, 8, 19), ("psychology", "Wednesday", "Psychology")),
    (date(2026, 8, 20), ("economics", "Thursday", "Economics")),
    (date(2026, 8, 21), ("science_technology", "Friday", "Science / Technology")),
    (date(2026, 8, 22), ("interesting_fact", "Saturday", "Interesting Fact")),
    (date(2026, 8, 23), ("quote_philosophy", "Sunday", "Quote / Philosophy")),
])
def test_weekday_mapping_is_fixed(selected_date, expected):
    thought = DailyThoughtService().get_thought(selected_date)
    assert (thought.category, thought.weekday, thought.category_label) == expected


def test_selection_is_stable_and_cycles_after_eight_matching_weekdays():
    service = DailyThoughtService()
    monday = date(2026, 8, 17)
    assert service.get_thought(monday) == service.get_thought(monday)
    rotation = [service.get_thought(date.fromordinal(monday.toordinal() + 7 * index)).id for index in range(8)]
    assert len(set(rotation)) == 8
    assert service.get_thought(date.fromordinal(monday.toordinal() + 7 * 8)).id == rotation[0]


def test_every_weekday_category_completes_a_full_rotation_and_handles_year_boundaries():
    service = DailyThoughtService()
    for selected_date in (date(2024, 12, 30), date(2024, 2, 26), date(2025, 1, 1), date(2026, 8, 23)):
        rotation = [service.get_thought(date.fromordinal(selected_date.toordinal() + 7 * index)) for index in range(8)]
        assert {thought.category for thought in rotation} == {rotation[0].category}
        assert len({thought.id for thought in rotation}) == 8


def test_content_audit_reports_counts_and_source_coverage():
    audit = audit_library()
    assert audit["total"] == 56
    assert audit["duplicate_ids"] == audit["duplicate_explanations"] == audit["duplicate_questions"] == []
    assert isinstance(audit["similar_titles"], list)
    assert {item["total"] for item in audit["categories"].values()} == {8}
    assert all(item["sourced"] + item["unsourced"] == 8 for item in audit["categories"].values())


def test_invalid_library_fails_validation(tmp_path):
    invalid = [{"id": "duplicate", "category": "history", "title": "Title", "what_it_is": "What", "why_it_matters": "Why", "think_about": "Question", "source_name": "Source", "source_url": "https://example.com/source"}] * 8
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError):
        DailyThoughtService(path).get_thought(date(2026, 8, 18))


def test_home_renders_the_daily_card_without_a_database_write(app, client, monkeypatch):
    selected_date = date(2026, 8, 17)
    monkeypatch.setattr(home, "current_date", lambda: selected_date)
    with app.app_context():
        before = (db.session.scalar(db.select(db.func.count(WeatherLocation.id))), db.session.scalar(db.select(db.func.count(CurrencyPair.id))))
    response = client.get("/")
    thought = DailyThoughtService().get_thought(selected_date)
    assert response.status_code == 200
    assert b"Something to think about" in response.data
    assert thought.title.replace("'", "&#39;") in response.get_data(as_text=True) and b"Think about" in response.data
    with app.app_context():
        after = (db.session.scalar(db.select(db.func.count(WeatherLocation.id))), db.session.scalar(db.select(db.func.count(CurrencyPair.id))))
    assert after == before


def test_home_escapes_daily_thought_content_and_secures_source_links(client, monkeypatch):
    thought = DailyThought("safe", "history", "Tuesday", "History", "<unsafe>", "<script>alert(1)</script>", "Why it matters", "Example", "What changes?", source_name="Source", source_url="https://example.com")

    class StubService:
        def get_thought(self, selected_date):
            return thought

    monkeypatch.setattr(home, "DailyThoughtService", StubService)
    response = client.get("/")
    assert b"&lt;unsafe&gt;" in response.data and b"&lt;script&gt;alert(1)&lt;/script&gt;" in response.data
    assert b'target="_blank" rel="noopener noreferrer"' in response.data


def test_weekday_category_configuration_has_all_days_in_order():
    assert [category for category, _, _ in WEEKDAY_CATEGORIES] == [
        "product_strategy", "history", "psychology", "economics", "science_technology", "interesting_fact", "quote_philosophy"
    ]
