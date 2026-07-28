from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


FEED_URL = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"
DEFAULT_SOURCE_URL = "https://en.wikipedia.org/wiki/Wikipedia:On_this_day/Today"


@dataclass(frozen=True)
class HistoricalEvent:
    year: int
    text: str
    source_url: str = DEFAULT_SOURCE_URL

    @property
    def year_label(self):
        return f"{abs(self.year)} BC" if self.year < 0 else str(self.year)


class OnThisDayService:
    def __init__(self, cache_path, timeout=1.5, fetcher=None):
        self.cache_path = Path(cache_path)
        self.timeout = timeout
        self.fetcher = fetcher or fetch_json
        self._failed_dates = set()

    def get_event(self, selected_date):
        cache_key = selected_date.strftime("%m-%d")
        cache = self._read_cache()
        cached_item = cache.get(cache_key)
        cached_event = event_from_cache(cached_item)

        if cached_event and cached_item.get("fetched_on") == selected_date.isoformat():
            return cached_event
        if selected_date.isoformat() in self._failed_dates:
            return cached_event

        try:
            payload = self.fetcher(
                FEED_URL.format(
                    month=selected_date.strftime("%m"),
                    day=selected_date.strftime("%d"),
                ),
                self.timeout,
            )
            event = select_event(payload, selected_date)
            if event is None:
                raise ValueError("Wikimedia response did not contain a usable event.")
            cache[cache_key] = {
                **asdict(event),
                "fetched_on": selected_date.isoformat(),
            }
            self._write_cache(cache)
            return event
        except Exception:
            self._failed_dates.add(selected_date.isoformat())
            return cached_event

    def _read_cache(self):
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_cache(self, cache):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.cache_path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self.cache_path)
        except OSError:
            # A cache write failure must never stop the homepage from loading.
            return


def fetch_json(url, timeout):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Joshs-Corner/1.0 (private local application)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def select_event(payload, selected_date):
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return None

    usable_events = []
    for item in payload["events"]:
        if not isinstance(item, dict) or not isinstance(item.get("year"), int):
            continue
        text = normalise_text(item.get("text"))
        if not text:
            continue
        usable_events.append(
            HistoricalEvent(
                year=item["year"],
                text=shorten(text),
                source_url=event_source_url(item),
            )
        )

    if not usable_events:
        return None

    concise_events = [event for event in usable_events if 45 <= len(event.text) <= 230]
    event_pool = concise_events or usable_events
    daily_seed = selected_date.year * 10000 + selected_date.month * 100 + selected_date.day
    return event_pool[daily_seed % len(event_pool)]


def event_from_cache(item):
    if not isinstance(item, dict):
        return None
    try:
        year = item["year"]
        text = normalise_text(item["text"])
        source_url = safe_source_url(item.get("source_url"))
    except (KeyError, TypeError):
        return None
    if not isinstance(year, int) or not text:
        return None
    return HistoricalEvent(year=year, text=shorten(text), source_url=source_url)


def event_source_url(item):
    try:
        candidate = item["pages"][0]["content_urls"]["desktop"]["page"]
    except (KeyError, IndexError, TypeError):
        return DEFAULT_SOURCE_URL
    return safe_source_url(candidate)


def safe_source_url(value):
    if not isinstance(value, str):
        return DEFAULT_SOURCE_URL
    parsed = urlparse(value)
    allowed_host = parsed.hostname and (
        parsed.hostname.endswith(".wikipedia.org")
        or parsed.hostname.endswith(".wikimedia.org")
    )
    return value if parsed.scheme == "https" and allowed_host else DEFAULT_SOURCE_URL


def normalise_text(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def shorten(value, maximum=190):
    if len(value) <= maximum:
        return value
    candidate = value[:maximum]
    last_space = candidate.rfind(" ")
    return candidate[: last_space if last_space > 120 else maximum].rstrip() + "…"
