from pathlib import Path


def test_homepage_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Josh's Corner" in response.data
    assert b"General Notes" in response.data
    assert b"Reading List" in response.data
    assert b"World Bank" in response.data
    assert b"Something to think about" in response.data
    assert b'target="_blank"' in response.data
    assert b'rel="noopener noreferrer"' in response.data


def test_shared_jz_favicon_assets_and_home_brand_are_available(client):
    homepage = client.get("/")
    assert b"Josh Zullo monogram" in homepage.data
    assert b"branding/jz-logo-192.png" in homepage.data
    assert b"branding/favicon.ico" in homepage.data
    assert b"jz-branding-1" in homepage.data

    for path in (
        "/static/branding/jz-logo-master-1024.png",
        "/static/branding/jz-logo-512.png",
        "/static/branding/jz-logo-192.png",
        "/static/branding/apple-touch-icon-180.png",
        "/static/branding/favicon-32.png",
        "/static/branding/favicon-16.png",
        "/static/branding/favicon.ico",
    ):
        assert client.get(path).status_code == 200


def test_shared_favicon_markup_is_present_on_direct_module_pages(client):
    for path in ("/", "/journal/", "/notes/", "/todos/", "/games/", "/watchlist/", "/reading/"):
        response = client.get(path)
        assert response.status_code == 200
        assert b"branding/favicon.ico" in response.data
        assert b"branding/favicon-32.png" in response.data


def test_shared_base_template_paints_a_dark_background_before_external_stylesheets(client):
    critical_style = b"<style>html,body{min-height:100%;background:#14121a}</style>"
    for path in ("/", "/journal/", "/notes/", "/todos/", "/games/", "/watchlist/", "/reading/"):
        response = client.get(path)
        assert critical_style in response.data
        assert response.data.index(critical_style) < response.data.index(b'/static/css/base.css')
        assert b"<script" not in response.data[:response.data.index(b'/static/css/base.css')]


def test_homepage_section_links_resolve(client):
    for path in ("/journal/", "/notes/", "/todos/", "/games/", "/watchlist/", "/reading/"):
        assert client.get(path).status_code == 200


def test_homepage_css_allows_vertical_scrolling():
    stylesheet = (Path(__file__).parents[1] / "app" / "static" / "css" / "home.css").read_text(encoding="utf-8")

    assert "overflow-y: auto;" in stylesheet
    assert ".home-page {\n  min-height: 100vh;\n  overflow: hidden;" not in stylesheet


def test_hub_uses_wide_centred_dashboards_and_stacks_utility_panels_before_mobile():
    stylesheet = (Path(__file__).parents[1] / "app" / "static" / "css" / "home.css").read_text(encoding="utf-8")

    assert ".top-dashboard { display:grid; grid-template-columns:minmax(0,3fr) minmax(300px,1fr);" in stylesheet
    assert ".thought-dashboard { width:min(1500px,calc(100vw - 7rem)); margin:var(--hub-section-gap) auto 0; display:grid; grid-template-columns:minmax(0,3fr) minmax(300px,1fr);" in stylesheet
    assert ".upcoming-block { min-width:0; grid-column:2; grid-row:1; }" in stylesheet
    assert "--hub-tile-row-height: 164px;" in stylesheet
    assert "height: calc((2 * var(--hub-tile-row-height)) + var(--hub-tile-row-gap));" in stylesheet
    assert "grid-template-rows: minmax(0, 1fr);" in stylesheet
    assert ".hub-utilities .deadlines-block,\n.hub-utilities .home-deadlines-card {\n  height: 100%;\n}" in stylesheet
    assert ".hub-utilities .home-deadlines-list {\n  flex: 1 1 auto;\n  min-height: 0;\n  overflow: hidden;\n}" in stylesheet
    assert "width: min(1500px, calc(100vw - 7rem));" in stylesheet
    assert "@media (max-width: 1199px) { .top-dashboard,.thought-dashboard { display:grid; grid-template-columns:1fr;" in stylesheet


def test_hub_panel_colours_and_vertical_rhythm_are_categorised_without_tile_changes():
    stylesheet = (Path(__file__).parents[1] / "app" / "static" / "css" / "home.css").read_text(encoding="utf-8")

    assert "--hub-section-gap:" in stylesheet
    assert "--deadline-border:" in stylesheet
    assert "--info-border:" in stylesheet
    assert ".home-deadlines-card,.daily-thought-card,.history-card,.figure-card" in stylesheet
    assert ".home-panels { display:grid; grid-template-columns:1fr; gap:var(--hub-section-gap); }" in stylesheet


def test_hub_panels_share_tile_style_edge_glow_shape_with_their_own_accents():
    stylesheet = (Path(__file__).parents[1] / "app" / "static" / "css" / "home.css").read_text(encoding="utf-8")

    assert "--hub-panel-edge-glow: var(--info-glow);" in stylesheet
    assert "--hub-panel-edge-glow: var(--deadline-glow);" in stylesheet
    assert "box-shadow: 0 0 18px 2px var(--hub-panel-edge-glow), inset 0 0 0 1px rgba(255, 255, 255, 0.01);" in stylesheet
from pathlib import Path
