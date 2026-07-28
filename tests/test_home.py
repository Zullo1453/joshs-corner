def test_homepage_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Josh's Corner" in response.data
    assert b"General Notes" in response.data
    assert b"Reading List" in response.data


def test_unbuilt_navigation_targets_use_the_shared_shell(client):
    for path in ("/games/", "/watchlist/", "/reading/"):
        response = client.get(path)
        assert response.status_code == 200
        assert b"Back to homepage" in response.data
        assert b"later approved stage" in response.data
