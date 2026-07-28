def test_homepage_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Josh's Corner" in response.data
    assert b"General Notes" in response.data
    assert b"Reading List" in response.data
    assert b"World Bank" in response.data
    assert b'target="_blank"' in response.data
    assert b'rel="noopener noreferrer"' in response.data


def test_homepage_section_links_resolve(client):
    for path in ("/journal/", "/notes/", "/todos/", "/games/", "/watchlist/", "/reading/"):
        assert client.get(path).status_code == 200


def test_homepage_css_allows_vertical_scrolling():
    stylesheet = (Path(__file__).parents[1] / "app" / "static" / "css" / "home.css").read_text(encoding="utf-8")

    assert "overflow-y: auto;" in stylesheet
    assert ".home-page {\n  min-height: 100vh;\n  overflow: hidden;" not in stylesheet
from pathlib import Path
