"""Provider-aware, resilient Interesting Figure of the Day service.

The curated local facts are deliberately static and work without a network
connection.  Live providers are refreshed no more frequently than every 90
days; a failed refresh is retried after 24 hours while any valid cached value
continues to be shown.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json
from pathlib import Path
from urllib.request import Request, urlopen


WORLD_BANK_API = "https://api.worldbank.org/v2/country/{scope}/indicator/{identifier}?format=json&per_page=100"
OWID_API = "https://ourworldindata.org/grapher/{identifier}.csv"
NOBEL_API = "https://api.nobelprize.org/v1/prize.json"
REFRESH_AFTER = timedelta(days=90)
RETRY_AFTER = timedelta(hours=24)


@dataclass(frozen=True)
class FigureEntry:
    key: str
    title: str
    category: str
    provider: str
    source_type: str
    scope: str
    scope_label: str
    identifier: str
    value_format: str
    context: str
    source_name: str
    source_url: str
    fallback_value: float
    fallback_year: int
    refresh_days: int | None = 90

    @property
    def is_live(self):
        return self.source_type in {"world_bank", "owid", "nobel"}


def wb(key, title, category, code, scope, scope_label, value_format, context, fallback, year):
    return FigureEntry(key, title, category, "World Bank", "world_bank", scope, scope_label, code, value_format, context,
                       "World Bank", f"https://data.worldbank.org/indicator/{code}?locations={scope}", fallback, year)


def owid(key, title, category, slug, value_format, context, fallback, year):
    return FigureEntry(key, title, category, "Our World in Data", "owid", "World", "World", slug, value_format, context,
                       "Our World in Data", f"https://ourworldindata.org/grapher/{slug}", fallback, year)


def nobel(key, title, category, identifier, context, fallback, year):
    return FigureEntry(key, title, category, "Nobel Prize", "nobel", "Global", "Global", identifier, "integer", context,
                       "Nobel Prize", "https://www.nobelprize.org/prizes/facts/nobel-prize-facts/", fallback, year)


def local(key, title, category, value_format, context, source_name, source_url, value, year):
    return FigureEntry(key, title, category, source_name, "local", "Global", "Global", key, value_format, context,
                       source_name, source_url, value, year, None)


FIGURES = (
    # Latest World Bank series.
    wb("wb_aus_gdp_pc", "GDP per capita", "Economy", "NY.GDP.PCAP.CD", "AUS", "Australia", "currency", "Economic output per person in current US dollars.", 65_000, 2023),
    wb("wb_world_population", "Population", "People", "SP.POP.TOTL", "WLD", "World", "compact", "Total population across reporting economies.", 8_100_000_000, 2024),
    wb("wb_aus_unemployment", "Unemployment", "Economy", "SL.UEM.TOTL.ZS", "AUS", "Australia", "percent", "Share of Australia’s total labour force without work.", 4.0, 2024),
    wb("wb_world_life_expectancy", "Life expectancy at birth", "Health", "SP.DYN.LE00.IN", "WLD", "World", "decimal", "Latest available global estimate, in years.", 73.3, 2023),
    wb("wb_aus_urbanisation", "Urban population", "Australia", "SP.URB.TOTL.IN.ZS", "AUS", "Australia", "percent", "Share of people living in urban areas.", 67.8, 2024),
    wb("wb_world_electricity", "Access to electricity", "Development", "EG.ELC.ACCS.ZS", "WLD", "World", "percent", "Share of people with access to electricity.", 91.0, 2022),
    wb("wb_aus_co2_pc", "CO₂ emissions per person", "Environment", "EN.ATM.CO2E.PC", "AUS", "Australia", "decimal", "Metric tons of carbon dioxide emissions per person.", 15.0, 2022),
    wb("wb_aus_education_spend", "Government education expenditure", "Australia", "SE.XPD.TOTL.GD.ZS", "AUS", "Australia", "percent", "Government education spending relative to GDP.", 5.0, 2022),
    wb("wb_world_trade", "Trade", "Economy", "NE.TRD.GNFS.ZS", "WLD", "World", "percent", "Value of goods and services trade relative to GDP.", 58.0, 2023),
    wb("wb_world_sanitation", "Safely managed sanitation", "Development", "SH.STA.SAN.AC.ZS", "WLD", "World", "percent", "Share of people using safely managed sanitation services.", 57.0, 2022),
    # OWID’s long-run and cross-source series (not a duplicate current Internet or poverty card).
    owid("owid_life_expectancy", "Life expectancy", "History", "life-expectancy", "decimal", "A long-run historical global series, in years.", 73.3, 2023),
    owid("owid_child_mortality", "Child mortality", "Health", "child-mortality", "decimal", "Deaths before age five per 1,000 live births.", 37.0, 2023),
    owid("owid_renewables", "Renewable electricity", "Energy", "share-electricity-renewables", "percent", "Share of global electricity generated from renewables.", 30.0, 2023),
    owid("owid_fossil_share", "Fossil-fuel electricity", "Energy", "share-electricity-fossil-fuels", "percent", "Share of global electricity generated from fossil fuels.", 61.0, 2023),
    owid("owid_forest_area", "Forest area", "Environment", "forest-area-km", "square_kilometres", "Global forest area, measured in square kilometres.", 40_000_000, 2025),
    owid("owid_literacy", "Adult literacy", "Education", "literacy-rate-adults", "percent", "Global adult literacy estimate; country reporting is uneven.", 87.0, 2022),
    owid("owid_food_supply", "Food supply", "Food", "daily-per-capita-caloric-supply", "integer", "Average daily food energy supply per person, in kilocalories.", 2_960, 2022),
    owid("owid_co2", "Carbon dioxide emissions", "Environment", "annual-co2-emissions-per-country", "compact", "Annual global fossil CO₂ emissions, in tonnes.", 37_000_000_000, 2023),
    owid("owid_air_passengers", "Air passengers", "Transport", "air-passengers-carried", "compact", "Commercial air passengers carried worldwide in a year.", 4_500_000_000, 2024),
    owid("owid_hours_worked", "Annual working hours", "Work", "annual-working-hours-per-worker", "integer", "Global average is an approximate, unevenly reported series.", 1_790, 2023),
    owid("owid_maternal_mortality", "Maternal mortality", "Health", "maternal-mortality", "decimal", "Maternal deaths per 100,000 live births.", 223.0, 2020),
    owid("owid_energy_use", "Energy use per person", "Energy", "per-capita-energy-use", "compact", "Average annual energy use per person, in kilowatt-hours.", 21_000, 2023),
    owid("owid_population_growth", "Population growth", "People", "population-growth-rate", "percent", "Annual global population growth rate.", 0.9, 2023),
    # Three varied Nobel API entries.
    nobel("nobel_first_year", "First Nobel Prizes", "History", "first_year", "The first Nobel Prizes were awarded in this year.", 1901, 1901),
    nobel("nobel_total_awards", "Nobel Prizes awarded", "Human achievement", "total_awards", "Total prizes awarded by the Nobel Prize organisation.", 627, 2024),
    nobel("nobel_physics_count", "Nobel Prizes in Physics", "Science", "physics_count", "Prizes awarded in the Physics category.", 118, 2024),
    # Fully offline, source-linked institutional facts.
    local("local_moonwalkers", "People who have walked on the Moon", "Space", "integer", "Twelve Apollo astronauts walked on the lunar surface.", "NASA", "https://science.nasa.gov/moon/humans-on-the-moon/", 12, 1972),
    local("local_lunar_landings", "Crewed Moon landings", "Space", "integer", "Six Apollo missions landed crews on the Moon.", "NASA", "https://science.nasa.gov/moon/exploration/apollo/", 6, 1972),
    local("local_age_earth", "Age of Earth", "Science", "compact_years", "Earth is about 4.54 billion years old.", "U.S. Geological Survey", "https://pubs.usgs.gov/gip/geotime/age.html", 4_540_000_000, 2024),
    local("local_age_universe", "Age of the universe", "Space", "compact_years", "The universe is about 13.8 billion years old.", "NASA", "https://science.nasa.gov/universe/overview/", 13_800_000_000, 2024),
    local("local_first_flight", "First powered flight", "Transport", "year", "The Wright brothers made their first sustained powered flight in this year.", "Smithsonian National Air and Space Museum", "https://airandspace.si.edu/stories/editorial/wright-brothers-first-flight", 1903, 1903),
    local("local_challenger_deep", "Challenger Deep depth", "Oceans", "depth", "Measurements vary; NOAA describes the deepest known point as about 11,000 metres below sea level.", "NOAA Ocean Service", "https://oceanservice.noaa.gov/facts/ocean-depth.html", 11_000, 2024),
    local("local_gbr_length", "Great Barrier Reef length", "Australia", "kilometres", "The Great Barrier Reef extends for about 2,300 kilometres.", "Great Barrier Reef Marine Park Authority", "https://www2.gbrmpa.gov.au/learn/reef-knowledge/reef-facts", 2_300, 2024),
    local("local_federation_year", "Australian Federation", "Australia", "year", "Australia became a federation on 1 January in this year.", "Parliament of Australia", "https://www.aph.gov.au/About_Parliament/House_of_Representatives/Powers_practice_n_procedure/Constitution", 1901, 1901),
    local("local_states_territories", "Australian states and mainland territories", "Australia", "states_territories", "Australia has 6 states and 2 mainland territories.", "Australian Government", "https://www.australia.gov.au/about-australia/our-country/our-states-and-territories", 8, 2024),
    local("local_sydney_opera_build", "Sydney Opera House construction period", "Australia", "years", "Construction ran from 1959 to its formal opening in 1973: a 14-year construction period.", "Sydney Opera House", "https://www.sydneyoperahouse.com/our-story/building-sydney-opera-house", 14, 1973),
    local("local_penicillin_year", "Penicillin Nobel Prize", "Medicine", "year", "Fleming, Chain and Florey received the Nobel Prize in Physiology or Medicine in this year.", "Nobel Prize", "https://www.nobelprize.org/prizes/medicine/1945/fleming/facts/", 1945, 1945),
    local("local_first_human_spaceflight", "First human spaceflight", "Space", "year", "Yuri Gagarin became the first human in space in this year.", "NASA", "https://www.nasa.gov/history/60-years-ago-yuri-gagarin-becomes-first-human-in-space/", 1961, 1961),
    local("local_metre_light_distance", "Light travelled in one metre", "Science", "integer", "One metre is the distance light travels in a vacuum in 1/299,792,458 of a second.", "BIPM", "https://www.bipm.org/en/si-base-units/metre", 299_792_458, 2019),
    local("local_antarctica_area", "Antarctica’s area", "Geography", "square_kilometres", "Antarctica covers about 14 million square kilometres.", "Australian Antarctic Program", "https://www.antarctica.gov.au/about-antarctica/fact-files/", 14_000_000, 2024),
    local("local_australia_area", "Australia’s area", "Australia", "square_kilometres", "Australia’s land area is about 7.7 million square kilometres.", "Geoscience Australia", "https://www.ga.gov.au/education/geoscience-basics/australias-size-compared", 7_692_024, 2024),
    local("local_hubble_launch", "Hubble Space Telescope launch", "Space", "year", "Hubble was launched into orbit in this year.", "NASA", "https://science.nasa.gov/mission/hubble/overview/", 1990, 1990),
    local("local_ozone_protocol", "Montreal Protocol", "Environment", "year", "The Montreal Protocol to protect the ozone layer was agreed in this year.", "UN Environment Programme", "https://www.unep.org/ozonaction/who-we-are/about-montreal-protocol", 1987, 1987),
    local("local_mars_rover_landing", "Perseverance Mars landing", "Space", "year", "NASA’s Perseverance rover landed on Mars in this year.", "NASA", "https://science.nasa.gov/mission/mars-2020-perseverance/", 2021, 2021),
    local("local_first_nations_continuity", "First Nations cultures in Australia", "Australia", "compact_years", "Aboriginal and Torres Strait Islander cultures have continued for more than 65,000 years.", "AIATSIS", "https://aiatsis.gov.au/explore/first-australians", 65_000, 2024),
    local("local_indigenous_languages", "Indigenous Australian languages", "Culture", "integer", "More than 250 Aboriginal and Torres Strait Islander languages were spoken at the time of colonisation.", "AIATSIS", "https://aiatsis.gov.au/explore/languages", 250, 2024),
    local("local_first_modern_olympics", "First modern Olympic Games", "Culture", "year", "The first modern Olympic Games were held in Athens in this year.", "Olympics", "https://olympics.com/ioc/faq/history-and-origin-of-the-games/when-were-the-first-modern-olympic-games-held", 1896, 1896),
    local("local_federal_womens_vote", "Federal women’s voting rights", "Australia", "year", "Australian women gained the federal vote in this year, subject to important historical exclusions.", "Australian Electoral Commission", "https://www.aec.gov.au/learn/history/womens-vote.htm", 1902, 1902),
    local("local_decimal_currency", "Australian decimal currency", "Australia", "year", "Australia introduced decimal currency in this year.", "Reserve Bank of Australia", "https://www.rba.gov.au/education/resources/explainers/australias-decimal-currency.html", 1966, 1966),
    local("local_voyager_launch", "Voyager 1 launch", "Space", "year", "Voyager 1 began its journey to the outer solar system in this year.", "NASA", "https://science.nasa.gov/mission/voyager/voyager-1/", 1977, 1977),
)

def _build_rotation(entries):
    """Interleave categories so consecutive days stay varied where possible."""
    remaining = list(entries)
    result = []
    previous_category = None
    while remaining:
        category_counts = {entry.category: sum(item.category == entry.category for item in remaining) for entry in remaining}
        candidates = [entry for entry in remaining if entry.category != previous_category] or remaining
        chosen = max(candidates, key=lambda entry: (category_counts[entry.category], -entries.index(entry)))
        result.append(chosen)
        remaining.remove(chosen)
        previous_category = chosen.category
    return tuple(result)


ROTATION = _build_rotation(FIGURES)
INDICATORS = FIGURES  # Compatibility alias for the existing local test fixture.


@dataclass(frozen=True)
class DailyFigure:
    entry: FigureEntry
    value: float
    year: int
    state: str

    @property
    def indicator(self):
        return self.entry

    @property
    def formatted_value(self):
        return format_value(self.value, self.entry.value_format)

    @property
    def source_url(self):
        return self.entry.source_url


class FigureOfDayService:
    def __init__(self, cache_path, timeout=2.0, fetcher=None, now=None):
        self.cache_path = Path(cache_path)
        self.timeout = timeout
        self.fetcher = fetcher or fetch_resource
        self.now = now or (lambda: datetime.now(timezone.utc))

    def get_figure(self, selected_date: date):
        entry = select_figure(selected_date)
        if not entry.is_live:
            return DailyFigure(entry, entry.fallback_value, entry.fallback_year, "curated")
        cache = self._read_cache()
        key = f"{selected_date.isoformat()}:{entry.key}"
        item = cache.get(key, {})
        cached = figure_from_cache(item, entry)
        current_time = self.now()
        if cached and is_fresh(item, current_time):
            return DailyFigure(entry, cached.value, cached.year, "cached")
        if not retry_due(item, current_time):
            return DailyFigure(entry, cached.value, cached.year, "previously_cached") if cached else fallback(entry)
        try:
            value, year = self._fetch_latest(entry)
            cache[key] = {"value": value, "year": year, "fetched_at": current_time.isoformat(), "last_attempt": current_time.isoformat()}
            self._write_cache(cache)
            return DailyFigure(entry, value, year, "live")
        except Exception:
            item["last_attempt"] = current_time.isoformat()
            cache[key] = item
            self._write_cache(cache)
            return DailyFigure(entry, cached.value, cached.year, "previously_cached") if cached else fallback(entry)

    def _fetch_latest(self, entry):
        if entry.source_type == "world_bank":
            return latest_world_bank_value(self.fetcher(WORLD_BANK_API.format(scope=entry.scope, identifier=entry.identifier), self.timeout))
        if entry.source_type == "owid":
            return latest_owid_value(self.fetcher(OWID_API.format(identifier=entry.identifier), self.timeout))
        return latest_nobel_value(self.fetcher(NOBEL_API, self.timeout), entry.identifier)

    def _read_cache(self):
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
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


def select_figure(selected_date):
    return ROTATION[selected_date.toordinal() % len(ROTATION)]


def fallback(entry):
    return DailyFigure(entry, entry.fallback_value, entry.fallback_year, "fallback")


def figure_from_cache(item, entry):
    if not isinstance(item, dict):
        return None
    value, year = item.get("value"), item.get("year")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isinstance(year, int):
        return DailyFigure(entry, float(value), year, "cached")
    return None


def parse_timestamp(value):
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def is_fresh(item, current_time):
    fetched_at = parse_timestamp(item.get("fetched_at")) if isinstance(item, dict) else None
    return bool(fetched_at and current_time - fetched_at < REFRESH_AFTER)


def retry_due(item, current_time):
    attempted_at = parse_timestamp(item.get("last_attempt")) if isinstance(item, dict) else None
    return not attempted_at or current_time - attempted_at >= RETRY_AFTER


def latest_world_bank_value(payload):
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("Malformed World Bank response")
    values = [(int(row["date"]), float(row["value"])) for row in payload[1]
              if isinstance(row, dict) and isinstance(row.get("value"), (int, float)) and not isinstance(row["value"], bool)
              and str(row.get("date", "")).isdigit()]
    if not values:
        raise ValueError("World Bank response has no usable value")
    year, value = max(values)
    return value, year


def latest_owid_value(payload):
    if not isinstance(payload, str):
        raise ValueError("Malformed OWID response")
    rows = list(csv.DictReader(io.StringIO(payload)))
    values = []
    for row in rows:
        if row.get("Entity") != "World":
            continue
        try:
            numeric = [float(value) for key, value in row.items() if key not in {"Entity", "Code", "Year"} and value not in (None, "")]
            values.append((int(row["Year"]), numeric[-1]))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    if not values:
        raise ValueError("OWID response has no World value")
    year, value = max(values)
    return value, year


def latest_nobel_value(payload, identifier):
    if not isinstance(payload, dict) or not isinstance(payload.get("prizes"), list):
        raise ValueError("Malformed Nobel response")
    prizes = payload["prizes"]
    if identifier == "first_year":
        years = [int(prize["year"]) for prize in prizes if str(prize.get("year", "")).isdigit()]
        return min(years), min(years)
    filtered = prizes if identifier == "total_awards" else [prize for prize in prizes if prize.get("category") == "physics"]
    years = [int(prize["year"]) for prize in filtered if str(prize.get("year", "")).isdigit()]
    if not years:
        raise ValueError("Nobel response has no usable value")
    return len(filtered), max(years)


def format_value(value, kind):
    if kind == "percent":
        return f"{value:.1f}%"
    if kind == "currency":
        return f"US${compact(value)}"
    if kind == "decimal":
        return f"{value:.1f}"
    if kind == "year":
        return str(int(value))
    if kind == "depth":
        return f"about {compact(value)} metres"
    if kind == "kilometres":
        return f"about {compact(value)} km"
    if kind == "square_kilometres":
        return f"about {compact(value)} km²"
    if kind == "compact_years":
        return f"about {compact(value)} years"
    if kind == "years":
        return f"{int(value)} years"
    if kind == "states_territories":
        return "6 states and 2 mainland territories"
    return compact(value)


def compact(value):
    for threshold, suffix in ((1_000_000_000_000, " trillion"), (1_000_000_000, " billion"), (1_000_000, " million")):
        if abs(value) >= threshold:
            return f"{value / threshold:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,.0f}"


def fetch_resource(url, timeout):
    request = Request(url, headers={"Accept": "application/json,text/csv", "User-Agent": "Joshs-Corner/1.0 (private local application)"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return body if url.endswith(".csv") else json.loads(body)
