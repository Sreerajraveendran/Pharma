"""Test fixtures.

Every run creates its own throwaway PostgreSQL database, `pharmacore_test_<random>`, applies
the real Alembic migrations to it (so the migrations are tested too), and drops it at the
end. Tests talk to the app through its HTTP API, in-process.

Server: set TEST_DATABASE_URL (a postgresql+asyncpg URL to any database on the server; it's
only used to create and drop the test database), or the POSTGRES_* credentials from .env are
used to reach 127.0.0.1:5432.
"""
import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url

ROOT = Path(__file__).resolve().parent.parent
TEST_DB_PREFIX = "pharmacore_test_"
TEST_DB = f"{TEST_DB_PREFIX}{uuid.uuid4().hex[:10]}"

BOOTSTRAP_EMAIL = "admin@test.local"
BOOTSTRAP_PASSWORD = "Bootstrap-Temp-Pass-1"
ADMIN_PASSWORD = "Granite-Harbor-Lantern-42"
RESET_PHRASE = "RESET DEMO DATA"


def _env_file() -> dict:
    values = {}
    path = ROOT.parent / ".env"  # the project root, next to docker-compose.yml
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def _server_url():
    if os.environ.get("TEST_DATABASE_URL"):
        return make_url(os.environ["TEST_DATABASE_URL"])
    env = _env_file()
    return make_url("postgresql+asyncpg://127.0.0.1:5432/postgres").set(
        username=env.get("POSTGRES_USER", "pharmacore"), password=env.get("POSTGRES_PASSWORD", ""))


SERVER_URL = _server_url()
ADMIN_DB_URL = SERVER_URL.set(database="postgres")
TEST_DB_URL = SERVER_URL.set(database=TEST_DB)
assert TEST_DB.startswith(TEST_DB_PREFIX)

# Configuration is read when the app modules are imported, so set it first
os.environ.update({
    "ENVIRONMENT": "development",
    "DATABASE_URL": TEST_DB_URL.render_as_string(hide_password=False),
    "DB_CONNECT_TIMEOUT_SECONDS": "10",
    "SEED_DEMO_DATA": "true",
    "ALLOW_DEMO_RESET": "true",
    "ALLOW_SELF_REGISTRATION": "true",
    "BOOTSTRAP_ADMIN_EMAIL": BOOTSTRAP_EMAIL,
    "BOOTSTRAP_ADMIN_PASSWORD": BOOTSTRAP_PASSWORD,
    "BOOTSTRAP_ADMIN_NAME": "System Administrator",
    "LOGIN_MAX_FAILED_ATTEMPTS": "3",
    "COOKIE_SECURE": "true",
})


async def _admin_execute(sql: str):
    import asyncpg
    conn = await asyncpg.connect(
        host=ADMIN_DB_URL.host, port=ADMIN_DB_URL.port or 5432, user=ADMIN_DB_URL.username,
        password=ADMIN_DB_URL.password, database=ADMIN_DB_URL.database)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def alembic(*args: str, url=TEST_DB_URL) -> subprocess.CompletedProcess:
    """Runs an Alembic command against a database (the test database by default)."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url.render_as_string(hide_password=False)}", *args],
        cwd=ROOT, capture_output=True, text=True)


def pytest_sessionstart(session):
    asyncio.run(_admin_execute(f'CREATE DATABASE "{TEST_DB}"'))
    result = alembic("upgrade", "head")
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stderr}")


def pytest_sessionfinish(session, exitstatus):
    # Only ever drop the per-run test database
    if TEST_DB.startswith(TEST_DB_PREFIX):
        asyncio.run(_admin_execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))


class StatementCounter:
    """Counts SQL statements, so tests can catch N+1 query regressions."""

    def __init__(self):
        self.enabled = False
        self.count = 0


STATEMENTS = StatementCounter()


@event.listens_for(Engine, "before_cursor_execute")
def _count_statement(conn, cursor, statement, parameters, context, executemany):
    if STATEMENTS.enabled and not statement.lstrip().upper().startswith(("BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE")):
        STATEMENTS.count += 1


async def count_statements(coro) -> tuple:
    """Runs an awaitable and returns (result, number of SQL statements it issued)."""
    STATEMENTS.count, STATEMENTS.enabled = 0, True
    try:
        result = await coro
    finally:
        STATEMENTS.enabled = False
    return result, STATEMENTS.count


class Api:
    """An API client with its own session cookie, sending the CSRF token on writes."""

    def __init__(self, client: httpx.AsyncClient):
        self.http = client
        self.csrf = None

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {}) or {}
        if self.csrf and method.upper() not in ("GET", "HEAD"):
            headers.setdefault("X-CSRF-Token", self.csrf)
        return await self.http.request(method, url, headers=headers, **kwargs)

    async def get(self, url, **kw): return await self.request("GET", url, **kw)
    async def post(self, url, **kw): return await self.request("POST", url, **kw)
    async def patch(self, url, **kw): return await self.request("PATCH", url, **kw)
    async def delete(self, url, **kw): return await self.request("DELETE", url, **kw)

    async def login(self, email: str, password: str) -> httpx.Response:
        res = await self.post("/api/auth/login", json={"email": email, "password": password})
        if res.status_code == 200:
            self.csrf = res.json()["csrf_token"]
        return res

    async def change_password(self, current: str, new: str) -> httpx.Response:
        res = await self.post("/api/auth/change-password", json={"current_password": current, "new_password": new})
        if res.status_code == 200:
            self.csrf = res.json()["csrf_token"]
        return res

    @property
    def session_cookie(self):
        return self.http.cookies.get("pc_session")


@pytest.fixture(scope="session")
async def app():
    from app.main import app as fastapi_app
    from app.db import engine as core

    assert core.database_name().startswith(TEST_DB_PREFIX), "refusing to run tests against a non-test database"
    async with LifespanManager(fastapi_app, startup_timeout=180, shutdown_timeout=30):
        yield fastapi_app


@pytest.fixture(scope="session")
async def make_client(app):
    clients = []

    def factory() -> Api:
        # https so the Secure session cookie is stored and sent back
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")
        api = Api(http)
        clients.append(api)
        return api

    yield factory
    for api in clients:
        await api.http.aclose()


@pytest.fixture(scope="session")
async def admin(make_client) -> Api:
    """The bootstrap administrator, signed in, with its password already changed."""
    api = make_client()
    res = await api.login(BOOTSTRAP_EMAIL, BOOTSTRAP_PASSWORD)
    assert res.status_code == 200, res.text
    res = await api.change_password(BOOTSTRAP_PASSWORD, ADMIN_PASSWORD)
    assert res.status_code == 200, res.text
    return api


class Db:
    """Direct SQL access to the test database, for checks the API doesn't expose."""

    async def all(self, sql: str, **params) -> list:
        from app.db.engine import connection
        async with connection() as conn:
            return [dict(r) for r in (await conn.execute(text(sql), params)).mappings()]

    async def one(self, sql: str, **params):
        rows = await self.all(sql, **params)
        return rows[0] if rows else None

    async def scalar(self, sql: str, **params):
        from app.db.engine import connection
        async with connection() as conn:
            return await conn.scalar(text(sql), params)

    async def execute(self, sql: str, **params):
        from app.db.engine import connection
        async with connection() as conn:
            await conn.execute(text(sql), params)


@pytest.fixture
def db(app) -> Db:
    return Db()


@pytest.fixture(scope="module")
async def demo_data(admin):
    """Fresh demo data for a module that changes it."""
    res = await admin.post("/api/settings/seed", json={"confirm": RESET_PHRASE})
    assert res.status_code == 200, res.text


async def make_user(admin: Api, make_client, role: str, email: str, full_name: str,
                    password: str = "Velvet-Orchid-Meadow-77") -> Api:
    """Creates a user with `role` and returns a signed-in client for it."""
    temp = "Temp-Silver-Brook-19"
    res = await admin.post("/api/users", json={"email": email, "full_name": full_name, "role": role, "password": temp})
    assert res.status_code == 201, res.text
    api = make_client()
    assert (await api.login(email, temp)).status_code == 200
    assert (await api.change_password(temp, password)).status_code == 200
    return api
