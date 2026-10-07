async def test_app_starts_and_serves(make_client):
    api = make_client()
    res = await api.get("/api/auth/config")
    assert res.status_code == 200
    assert res.json()["registration_enabled"] is True


async def test_admin_fixture_signs_in(admin):
    res = await admin.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "admin"
