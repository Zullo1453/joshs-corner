"""Curated World Bank figure-of-the-day service with resilient local caching."""
from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
from urllib.request import Request, urlopen


API_URL = "https://api.worldbank.org/v2/country/{scope}/indicator/{code}?format=json&per_page=100"


@dataclass(frozen=True)
class Indicator:
    code: str
    title: str
    unit: str
    scope: str
    scope_label: str
    context: str
    format: str


INDICATORS = (
    Indicator("SP.URB.TOTL.IN.ZS", "Urban population", "%", "AUS", "Australia", "Share of people living in urban areas.", "percent"),
    Indicator("SP.POP.TOTL", "Population", "people", "WLD", "World", "Total population across reporting economies.", "compact"),
    Indicator("SH.STA.SAN.AC.ZS", "Safely managed sanitation services", "%", "WLD", "World", "Share of people using safely managed sanitation services.", "percent"),
    Indicator("EG.ELC.ACCS.ZS", "Access to electricity", "%", "WLD", "World", "Share of people with access to electricity.", "percent"),
    Indicator("IT.NET.USER.ZS", "Individuals using the Internet", "%", "WLD", "World", "Share of people using the Internet.", "percent"),
    Indicator("NY.GDP.PCAP.CD", "GDP per capita", "current US$", "AUS", "Australia", "Economic output per person in current US dollars.", "currency"),
    Indicator("SL.UEM.TOTL.ZS", "Unemployment", "% of labour force", "AUS", "Australia", "Share of the total labour force without work.", "percent"),
    Indicator("EN.ATM.CO2E.PC", "CO₂ emissions", "metric tons per person", "AUS", "Australia", "Carbon dioxide emissions per person.", "decimal"),
    Indicator("SE.XPD.TOTL.GD.ZS", "Government education expenditure", "% of GDP", "AUS", "Australia", "Government education spending relative to GDP.", "percent"),
    Indicator("NE.TRD.GNFS.ZS", "Trade", "% of GDP", "WLD", "World", "Value of goods and services trade relative to GDP.", "percent"),
)

FALLBACKS = {
    "SP.URB.TOTL.IN.ZS": (67.8, 2024),
    "SP.POP.TOTL": (8_100_000_000, 2024),
    "SH.STA.SAN.AC.ZS": (57.0, 2022),
    "EG.ELC.ACCS.ZS": (91.0, 2022),
    "IT.NET.USER.ZS": (68.0, 2024),
    "NY.GDP.PCAP.CD": (65_000, 2023),
    "SL.UEM.TOTL.ZS": (4.0, 2024),
    "EN.ATM.CO2E.PC": (15.0, 2022),
    "SE.XPD.TOTL.GD.ZS": (5.0, 2022),
    "NE.TRD.GNFS.ZS": (58.0, 2023),
}


@dataclass(frozen=True)
class DailyFigure:
    indicator: Indicator
    value: float
    year: int
    state: str

    @property
    def formatted_value(self):
        return format_value(self.value, self.indicator.format)


class FigureOfDayService:
    def __init__(self, cache_path, timeout=2.0, fetcher=None):
        self.cache_path = Path(cache_path)
        self.timeout = timeout
        self.fetcher = fetcher or fetch_json
        self._failed_dates = set()

    def get_figure(self, selected_date: date):
        indicator = select_indicator(selected_date)
        key = f"{selected_date.isoformat()}:{indicator.code}"
        cache = self._read_cache()
        cached = figure_from_cache(cache.get(key), indicator)
        if cached:
            return cached
        if key not in self._failed_dates:
            try:
                figure = DailyFigure(indicator, *latest_value(self.fetcher(API_URL.format(scope=indicator.scope, code=indicator.code), self.timeout)), "live")
                cache[key] = {"value": figure.value, "year": figure.year}
                self._write_cache(cache)
                return figure
            except Exception:
                self._failed_dates.add(key)
        previous = next((figure_from_cache(item, indicator_from_key(k)) for k, item in cache.items() if figure_from_cache(item, indicator_from_key(k))), None)
        if previous:
            return DailyFigure(previous.indicator, previous.value, previous.year, "previously_cached")
        value, year = FALLBACKS[indicator.code]
        return DailyFigure(indicator, value, year, "fallback")

    def _read_cache(self):
        try:
            result = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return result if isinstance(result, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_cache(self, cache):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            temporary.replace(self.cache_path)
        except OSError:
            pass


def select_indicator(selected_date):
    return INDICATORS[selected_date.toordinal() % len(INDICATORS)]


def indicator_from_key(key):
    code = key.rsplit(":", 1)[-1]
    return next((indicator for indicator in INDICATORS if indicator.code == code), None)


def figure_from_cache(item, indicator):
    if indicator is None or not isinstance(item, dict):
        return None
    value, year = item.get("value"), item.get("year")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isinstance(year, int):
        return DailyFigure(indicator, value, year, "cached")
    return None


def latest_value(payload):
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("Malformed World Bank response")
    values = []
    for row in payload[1]:
        if not isinstance(row, dict) or not isinstance(row.get("value"), (int, float)) or isinstance(row["value"], bool):
            continue
        try:
            values.append((int(row["date"]), float(row["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not values:
        raise ValueError("World Bank response has no usable value")
    year, value = max(values)
    return value, year


def format_value(value, kind):
    if kind == "percent":
        return f"{value:.1f}%".rstrip("0").rstrip(".") + "%" if False else f"{value:.1f}%"
    if kind == "currency":
        return f"US${compact(value)}"
    if kind == "decimal":
        return f"{value:.1f}"
    return compact(value)


def compact(value):
    for threshold, suffix in ((1_000_000_000_000, " trillion"), (1_000_000_000, " billion"), (1_000_000, " million")):
        if abs(value) >= threshold:
            return f"{value / threshold:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,.0f}"


def fetch_json(url, timeout):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Joshs-Corner/1.0 (private local application)"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
