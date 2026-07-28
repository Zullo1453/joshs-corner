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
