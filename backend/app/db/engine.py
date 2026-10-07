"""PostgreSQL connection management.

Repositories run queries through `connection()`. Inside `async with transaction():` every
query shares one connection and one transaction (the current one is kept in a ContextVar),
so a service can make several repository calls atomically; outside it, each call runs in
its own short transaction.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import AsyncIterator, Optional

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core import config

logger = logging.getLogger("app.db.engine")

# The backend folder: holds alembic.ini and alembic/ (/app inside the Docker image)
BACKEND_DIR = Path(__file__).resolve().parents[2]

engine: Optional[AsyncEngine] = None
_current: ContextVar[Optional[AsyncConnection]] = ContextVar("current_db_connection", default=None)


class DatabaseUnavailable(RuntimeError):
    pass


def redacted_url(url: str = None) -> str:
    """The database URL without credentials or driver (postgresql://host:5432/db), safe for
    logs and the status endpoint."""
    parsed = make_url(url or config.DATABASE_URL)
    return f"postgresql://{parsed.host}:{parsed.port or 5432}/{parsed.database or ''}"


def database_name() -> str:
    return make_url(config.DATABASE_URL).database or ""


async def init_db():
    """Connects (retrying while the server starts) and checks the schema is up to date."""
    global engine
    logger.info(f"Connecting to PostgreSQL at {redacted_url()}...")
    engine = create_async_engine(config.DATABASE_URL, pool_size=config.DB_POOL_SIZE,
                                 max_overflow=config.DB_POOL_SIZE, pool_pre_ping=True)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + config.DB_CONNECT_TIMEOUT_SECONDS
    while True:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            break
        except Exception as e:
            if loop.time() >= deadline:
                await engine.dispose()
                engine = None
                raise DatabaseUnavailable(
                    f"Could not connect to PostgreSQL at {redacted_url()} within "
                    f"{config.DB_CONNECT_TIMEOUT_SECONDS}s: {type(e).__name__}: {e}. Check that the server is "
                    "running and DATABASE_URL (including credentials) is correct.") from None
            logger.warning(f"PostgreSQL not reachable yet ({type(e).__name__}); retrying...")
            await asyncio.sleep(2)
    await _check_schema_current()
    logger.info(f"Connected to PostgreSQL at {redacted_url()}")


async def _check_schema_current():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_current_head()
    async with engine.connect() as conn:
        exists = await conn.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
        current = await conn.scalar(text("SELECT version_num FROM alembic_version")) if exists else None
    if current != head:
        raise DatabaseUnavailable(
            f"The database schema is at revision {current or 'none'}, but the code needs {head}. "
            "Run `alembic upgrade head` (the Docker image does this on start).")


async def close_db():
    global engine
    if engine is not None:
        await engine.dispose()
    engine = None


def _require_engine() -> AsyncEngine:
    if engine is None:
        raise DatabaseUnavailable("Database not initialised; init_db() must run first")
    return engine


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncConnection]:
    """One transaction for everything inside the block (joins an enclosing one)."""
    existing = _current.get()
    if existing is not None:
        yield existing
        return
    async with _require_engine().begin() as conn:
        token = _current.set(conn)
        try:
            yield conn
        finally:
            _current.reset(token)


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    """The current transaction's connection, or a short transaction of its own."""
    existing = _current.get()
    if existing is not None:
        yield existing
        return
    async with _require_engine().begin() as conn:
        yield conn


@asynccontextmanager
async def streaming_connection() -> AsyncIterator[AsyncConnection]:
    """A dedicated connection for server-side cursors (e.g. CSV export streaming)."""
    async with _require_engine().connect() as conn:
        yield conn
