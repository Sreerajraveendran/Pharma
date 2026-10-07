"""Application state (e.g. the demo-data marker) and the demo-reset wipe."""
from typing import Optional

from sqlalchemy import delete, exists, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.engine import connection
from app.db.tables import BUSINESS_TABLES, app_meta, metadata


async def get(key: str) -> Optional[dict]:
    async with connection() as conn:
        return await conn.scalar(select(app_meta.c.value).where(app_meta.c.key == key))


async def put(key: str, value: dict):
    stmt = pg_insert(app_meta).values(key=key, value=value)
    async with connection() as conn:
        await conn.execute(stmt.on_conflict_do_update(index_elements=[app_meta.c.key], set_={"value": value}))


async def remove(key: str):
    async with connection() as conn:
        await conn.execute(delete(app_meta).where(app_meta.c.key == key))


async def has_business_data() -> bool:
    async with connection() as conn:
        for name in BUSINESS_TABLES:
            if await conn.scalar(select(exists().select_from(metadata.tables[name]))):
                return True
    return False


async def wipe_business_data():
    """Deletes every business table in one statement (users, sessions and auth events stay)
    and restarts invoice numbering."""
    async with connection() as conn:
        await conn.execute(text("TRUNCATE " + ", ".join(BUSINESS_TABLES)))
        await conn.execute(text("ALTER SEQUENCE invoice_number_seq RESTART"))
