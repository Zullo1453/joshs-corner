from datetime import date

from app.figure_of_day import FigureOfDayService, INDICATORS, format_value, latest_value, select_indicator


def test_selection_is_deterministic_and_curated():
    selected = date(2026, 7, 28)
    assert select_indicator(selected) == select_indicator(selected)
    assert select_indicator(selected) in INDICATORS


def test_latest_non_null_value_and_formatting():
    payload = [{}, [{"date": "2022", "value": 2}, {"date": "2024", "value": None}, {"date": "2023", "value": 3.4}]]
    assert latest_value(payload) == (3.4, 2023)
    assert format_value(2_400_000_000, "compact") == "2.4 billion"
    assert format_value(67.8, "percent") == "67.8%"


def test_cache_offline_and_fallback_are_safe(tmp_path):
    service = FigureOfDayService(tmp_path / "figure.json", fetcher=lambda url, timeout: [{}, [{"date": "2023", "value": 7.5}]])
    selected = date(2026, 7, 28)
    live = service.get_figure(selected)
    assert live.state == "live" and live.year == 2023
    cached = FigureOfDayService(tmp_path / "figure.json", fetcher=lambda *_: (_ for _ in ()).throw(TimeoutError())).get_figure(selected)
    assert cached.state == "cached"
    fallback = FigureOfDayService(tmp_path / "empty.json", fetcher=lambda *_: (_ for _ in ()).throw(TimeoutError())).get_figure(selected)
    assert fallback.state == "fallback"
    assert fallback.source_url.startswith("https://data.worldbank.org/")
