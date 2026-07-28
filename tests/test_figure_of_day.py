from datetime import date, datetime, timedelta, timezone

from app.figure_of_day import FIGURES, ROTATION, FigureOfDayService, format_value, select_figure


def fixed_now(value):
    return lambda: value


def world_bank_payload(value=7.5, year="2023"):
    return [{}, [{"date": year, "value": value}]]


def test_curated_bank_has_balanced_provider_counts_and_unique_keys():
    assert len(FIGURES) == 50
    assert len({entry.key for entry in FIGURES}) == 50
    assert sum(entry.provider == "World Bank" for entry in FIGURES) == 10
    assert sum(entry.provider == "Our World in Data" for entry in FIGURES) == 13
    assert sum(entry.source_type == "nobel" for entry in FIGURES) == 3
    assert sum(entry.source_type == "local" for entry in FIGURES) == 24
    assert all(entry.source_url.startswith("https://") for entry in FIGURES)


def test_rotation_is_deterministic_and_selects_every_entry():
    selected = {select_figure(date.fromordinal(day)).key for day in range(730000, 730050)}
    assert len(selected) == len(FIGURES)
    assert all(first.category != second.category for first, second in zip(ROTATION, ROTATION[1:]))


def test_live_result_is_cached_for_ninety_days(tmp_path):
    selected = date(2026, 1, 1)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = FigureOfDayService(tmp_path / "figure.json", fetcher=lambda *_: world_bank_payload(), now=fixed_now(now))
    # Choose a date that maps to a World Bank entry.
    selected = next(date.fromordinal(day) for day in range(730000, 730100) if select_figure(date.fromordinal(day)).source_type == "world_bank")
    live = service.get_figure(selected)
    assert live.state == "live"
    cached = FigureOfDayService(tmp_path / "figure.json", fetcher=lambda *_: (_ for _ in ()).throw(TimeoutError()), now=fixed_now(now + timedelta(days=89))).get_figure(selected)
    assert cached.state == "cached"


def test_stale_cache_survives_failure_and_retries_after_day(tmp_path):
    selected = next(date.fromordinal(day) for day in range(730000, 730100) if select_figure(date.fromordinal(day)).source_type == "world_bank")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cache = tmp_path / "figure.json"
    FigureOfDayService(cache, fetcher=lambda *_: world_bank_payload(), now=fixed_now(now)).get_figure(selected)
    failed = FigureOfDayService(cache, fetcher=lambda *_: (_ for _ in ()).throw(TimeoutError()), now=fixed_now(now + timedelta(days=91)))
    assert failed.get_figure(selected).state == "previously_cached"
    assert failed.get_figure(selected).state == "previously_cached"
    retry = FigureOfDayService(cache, fetcher=lambda *_: world_bank_payload(9.0, "2024"), now=fixed_now(now + timedelta(days=92, hours=1)))
    assert retry.get_figure(selected).state == "live"


def test_local_facts_are_offline_and_source_linked(tmp_path):
    selected = next(date.fromordinal(day) for day in range(730000, 730100) if select_figure(date.fromordinal(day)).source_type == "local")
    figure = FigureOfDayService(tmp_path / "figure.json", fetcher=lambda *_: (_ for _ in ()).throw(AssertionError())).get_figure(selected)
    assert figure.state == "curated"
    assert figure.source_url.startswith("https://")


def test_owid_and_nobel_parsers_accept_offline_fixture_data(tmp_path):
    owid_date = next(date.fromordinal(day) for day in range(730000, 730100) if select_figure(date.fromordinal(day)).source_type == "owid")
    nobel_date = next(date.fromordinal(day) for day in range(730000, 730100) if select_figure(date.fromordinal(day)).source_type == "nobel")
    def fetcher(url, _timeout):
        if url.endswith(".csv"):
            return "Entity,Code,Year,Value\nWorld,OWID_WRL,2024,42.5\n"
        return {"prizes": [{"year": "1901", "category": "physics"}, {"year": "2024", "category": "physics"}]}
    service = FigureOfDayService(tmp_path / "figure.json", fetcher=fetcher)
    assert service.get_figure(owid_date).state == "live"
    assert service.get_figure(nobel_date).state == "live"


def test_format_value():
    assert format_value(65_000, "currency") == "US$65,000"
    assert format_value(67.8, "percent") == "67.8%"
    assert format_value(8, "states_territories") == "6 states and 2 mainland territories"
