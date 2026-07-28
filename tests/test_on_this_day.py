from datetime import date
import json
from urllib.error import URLError

import pytest

from app.on_this_day import HistoricalEvent, OnThisDayService


WIKIMEDIA_PAYLOAD = {
    "events": [
        {"year": 10, "text": "Too short"},
        {
            "year": 1914,
            "text": "Austria-Hungary declared war on Serbia, beginning World War I.",
            "pages": [
                {
                    "content_urls": {
                        "desktop": {
                            "page": "https://en.wikipedia.org/wiki/July_Crisis"
                        }
                    }
                }
            ],
        },
    ]
}


def test_successful_wikimedia_response_is_selected_and_cached(tmp_path):
    calls = []

    def fetcher(url, timeout):
        calls.append((url, timeout))
        return WIKIMEDIA_PAYLOAD

    cache_path = tmp_path / "on_this_day_cache.json"
    service = OnThisDayService(cache_path, timeout=1.25, fetcher=fetcher)

    event = service.get_event(date(2026, 7, 28))

    assert event.year == 1914
    assert event.text == "Austria-Hungary declared war on Serbia, beginning World War I."
    assert event.source_url == "https://en.wikipedia.org/wiki/July_Crisis"
    assert calls == [
        (
            "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/07/28",
            1.25,
        )
    ]
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached["07-28"]["year"] == 1914
    assert cached["07-28"]["fetched_on"] == "2026-07-28"


def test_same_day_cache_avoids_another_request(tmp_path):
    cache_path = tmp_path / "on_this_day_cache.json"
    first = OnThisDayService(cache_path, fetcher=lambda url, timeout: WIKIMEDIA_PAYLOAD)
    first.get_event(date(2026, 7, 28))

    second = OnThisDayService(
        cache_path,
        fetcher=lambda url, timeout: pytest.fail("Network should not be called"),
    )

    assert second.get_event(date(2026, 7, 28)).year == 1914


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"events": []},
        {"events": [{"year": "not-an-integer", "text": "Malformed"}]},
        {"events": [{"year": 2000, "text": ""}]},
    ],
)
def test_malformed_or_empty_response_uses_no_cache_fallback(tmp_path, payload):
    service = OnThisDayService(
        tmp_path / "cache.json",
        fetcher=lambda url, timeout: payload,
    )

    assert service.get_event(date(2026, 7, 28)) is None


@pytest.mark.parametrize("error", [TimeoutError(), URLError("offline")])
def test_timeout_and_api_failure_without_cache_return_none(tmp_path, error):
    def failing_fetcher(url, timeout):
        raise error

    service = OnThisDayService(tmp_path / "cache.json", fetcher=failing_fetcher)

    assert service.get_event(date(2026, 7, 28)) is None


def test_cached_event_is_used_after_network_failure(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "07-28": {
                    "year": 1965,
                    "text": "A previously cached historical event.",
                    "source_url": "https://en.wikipedia.org/wiki/History",
                    "fetched_on": "2025-07-28",
                }
            }
        ),
        encoding="utf-8",
    )

    def failing_fetcher(url, timeout):
        raise TimeoutError

    service = OnThisDayService(cache_path, fetcher=failing_fetcher)
    event = service.get_event(date(2026, 7, 28))

    assert event == HistoricalEvent(
        year=1965,
        text="A previously cached historical event.",
        source_url="https://en.wikipedia.org/wiki/History",
    )


def test_homepage_renders_selected_event(client, app, monkeypatch):
    from app.routes import home

    class SuccessfulService:
        def get_event(self, selected_date):
            assert selected_date == date(2026, 7, 28)
            return HistoricalEvent(
                year=1914,
                text="Austria-Hungary declared war on Serbia, beginning World War I.",
                source_url="https://en.wikipedia.org/wiki/July_Crisis",
            )

    monkeypatch.setattr(home, "current_date", lambda: date(2026, 7, 28))
    app.extensions["on_this_day"] = SuccessfulService()
    response = client.get("/")

    assert response.status_code == 200
    assert b"On this day" in response.data
    assert b"28 July" in response.data
    assert b"1914" in response.data
    assert b"Austria-Hungary declared war on Serbia" in response.data
    assert b"https://en.wikipedia.org/wiki/July_Crisis" in response.data


def test_homepage_still_loads_when_service_raises(client, app):
    class BrokenService:
        def get_event(self, selected_date):
            raise RuntimeError("unexpected service failure")

    app.extensions["on_this_day"] = BrokenService()
    response = client.get("/")

    assert response.status_code == 200
    assert b"Historical event unavailable while offline." in response.data
    assert b"Josh's Corner" in response.data
