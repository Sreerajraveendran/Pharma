"""Authentication, sessions, CSRF, roles, user administration and self-registration."""
import uuid

from conftest import ADMIN_PASSWORD, BOOTSTRAP_EMAIL, make_user

INVALID = "Invalid email or password."


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6]}@test.local"


async def test_protected_routes_need_a_session(make_client):
    anon = make_client()
    for method, url in [("GET", "/api/medicines"), ("GET", "/api/billing/invoices/export/csv"),
                        ("POST", "/api/settings/seed"), ("GET", "/api/users")]:
        res = await anon.request(method, url)
        assert res.status_code == 401, (method, url, res.status_code)


async def test_failed_logins_look_identical(make_client, admin):
    anon = make_client()
    wrong_pw = await anon.login(BOOTSTRAP_EMAIL, "wrong-password-123")
    no_user = await anon.login("nobody@test.local", "wrong-password-123")
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"] == INVALID


async def test_session_cookie_flags(make_client, admin):
    api = make_client()
    res = await api.login(BOOTSTRAP_EMAIL, ADMIN_PASSWORD)
    assert res.status_code == 200
    cookie = res.headers["set-cookie"].lower()
    for flag in ("httponly", "secure", "samesite=strict", "path=/api"):
        assert flag in cookie
    body = res.text
    assert api.session_cookie not in body, "the session token must never appear in a response body"
    assert res.headers["cache-control"] == "no-store"


async def test_csrf_required_for_writes(make_client, admin):
    api = make_client()
    await api.login(BOOTSTRAP_EMAIL, ADMIN_PASSWORD)
    res = await api.post("/api/auth/change-password", headers={"X-CSRF-Token": "forged"},
                         json={"current_password": ADMIN_PASSWORD, "new_password": "Another-Long-Phrase-9"})
    assert res.status_code == 403 and "CSRF" in res.json()["detail"]


async def test_new_account_must_change_password_first(make_client, admin):
    email = unique_email("newbie")
    res = await admin.post("/api/users", json={"email": email, "full_name": "Neha New", "role": "cashier",
                                               "password": "Temp-Silver-Brook-19"})
    assert res.status_code == 201
    api = make_client()
    res = await api.login(email, "Temp-Silver-Brook-19")
    assert res.json()["user"]["must_change_password"] is True
    assert (await api.get("/api/medicines")).json()["detail"] == "Password change required"
    assert (await api.change_password("Temp-Silver-Brook-19", "short")).status_code == 400
    res = await api.change_password("Temp-Silver-Brook-19", "Copper-Willow-Sunrise-8")
    assert res.status_code == 200 and res.json()["user"]["must_change_password"] is False
    assert (await api.get("/api/medicines")).status_code == 200


async def test_status_never_exposes_db_credentials(admin):
    res = await admin.get("/api/settings/status")
    assert res.status_code == 200 and "@" not in res.json()["database_url"]


async def test_cashier_permissions(make_client, admin):
    cashier = await make_user(admin, make_client, "cashier", unique_email("cashier"), "Casey Cashier")
    assert (await cashier.get("/api/medicines")).status_code == 200
    for method, url, body in [
        ("POST", "/api/medicines", {"name": "x"}),
        ("POST", "/api/settings/seed", {"confirm": "RESET DEMO DATA"}),
        ("GET", "/api/users", None),
        ("DELETE", "/api/billing/invoices/INV-1", None),
    ]:
        res = await cashier.request(method, url, json=body) if body is not None else await cashier.request(method, url)
        assert res.status_code == 403, (method, url, res.status_code)


async def test_duplicate_user_email_rejected(admin):
    email = unique_email("dup")
    body = {"email": email, "full_name": "Dup", "role": "cashier", "password": "Temp-Silver-Brook-19"}
    assert (await admin.post("/api/users", json=body)).status_code == 201
    assert (await admin.post("/api/users", json={**body, "email": email.upper()})).status_code == 409


async def test_role_change_and_disable_revoke_sessions(make_client, admin):
    email = unique_email("promo")
    user = await make_user(admin, make_client, "cashier", email, "Pat Promo")
    user_id = (await user.get("/api/auth/me")).json()["user"]["id"]

    res = await admin.patch(f"/api/users/{user_id}", json={"role": "pharmacist"})
    assert res.status_code == 200 and res.json()["role"] == "pharmacist"
    assert (await user.get("/api/medicines")).status_code == 401, "role change must end existing sessions"

    assert (await admin.patch(f"/api/users/{user_id}", json={"is_active": False})).status_code == 200
    assert (await make_client().login(email, "Velvet-Orchid-Meadow-77")).status_code == 401


async def test_last_admin_cannot_be_demoted(admin):
    me = (await admin.get("/api/auth/me")).json()["user"]["id"]
    res = await admin.patch(f"/api/users/{me}", json={"role": "cashier"})
    assert res.status_code == 400


async def test_lockout_after_repeated_failures(make_client, admin):
    email = unique_email("lock")
    await make_user(admin, make_client, "cashier", email, "Lou Lock")
    api = make_client()
    for _ in range(3):  # LOGIN_MAX_FAILED_ATTEMPTS=3 in tests
        await api.login(email, "nope-nope-nope")
    res = await api.login(email, "Velvet-Orchid-Meadow-77")
    assert res.status_code == 401, "correct password must be refused while locked"


async def test_logout_invalidates_the_session(make_client, admin):
    api = make_client()
    await api.login(BOOTSTRAP_EMAIL, ADMIN_PASSWORD)
    old_cookie = api.session_cookie
    assert (await api.post("/api/auth/logout")).status_code == 204
    replay = make_client()
    replay.http.cookies.set("pc_session", old_cookie, domain="test", path="/api")
    assert (await replay.get("/api/medicines")).status_code == 401


# Self-registration

async def test_registration_flow(make_client, admin):
    email = unique_email("hire")
    anon = make_client()
    cfg = (await anon.get("/api/auth/config")).json()
    assert cfg["registration_enabled"] is True

    first = await anon.post("/api/auth/register", json={"email": email, "full_name": "Nina Newhire",
                                                        "password": "Copper-Willow-Sunrise-8", "role": "admin"})
    again = await anon.post("/api/auth/register", json={"email": email, "full_name": "Someone Else",
                                                        "password": "Another-Valid-Phrase-3"})
    assert first.status_code == again.status_code == 202
    assert first.json() == again.json(), "duplicate registration must not reveal the account exists"

    assert (await anon.post("/api/auth/register", json={"email": "weak@test.local", "full_name": "W", "password": "short"})).status_code == 400
    assert (await anon.post("/api/auth/register", json={"email": "not-an-email", "full_name": "X", "password": "Copper-Willow-Sunrise-8"})).status_code == 422

    pending = await make_client().login(email, "Copper-Willow-Sunrise-8")
    assert pending.status_code == 403 and "approval" in pending.json()["detail"]
    wrong = await make_client().login(email, "Wrong-Password-Here-1")
    assert wrong.status_code == 401 and wrong.json()["detail"] == INVALID

    users = (await admin.get("/api/users")).json()
    newbie = next(u for u in users if u["email"] == email)
    assert newbie["pending_approval"] and not newbie["is_active"]
    assert newbie["role"] == "cashier", "self-registration must ignore a requested role"

    res = await admin.patch(f"/api/users/{newbie['id']}", json={"role": "pharmacist", "is_active": True})
    assert res.status_code == 200 and not res.json()["pending_approval"]
    approved = make_client()
    res = await approved.login(email, "Copper-Willow-Sunrise-8")
    assert res.status_code == 200 and not res.json()["user"]["must_change_password"]
    assert (await approved.post("/api/categories", json={"name": f"Cat {uuid.uuid4().hex[:4]}", "color_code": "#000000"})).status_code == 201
    assert (await admin.delete(f"/api/users/{newbie['id']}")).status_code == 400, "approved accounts are disabled, not deleted"


async def test_rejected_registration_is_deleted(make_client, admin):
    email = unique_email("spam")
    await make_client().post("/api/auth/register", json={"email": email, "full_name": "Spam Bot", "password": "Hazel-Quartz-River-9"})
    spam = next(u for u in (await admin.get("/api/users")).json() if u["email"] == email)
    assert (await admin.delete(f"/api/users/{spam['id']}")).status_code == 204
    assert (await make_client().login(email, "Hazel-Quartz-River-9")).status_code == 401
    assert (await make_client().delete(f"/api/users/{spam['id']}")).status_code == 401
