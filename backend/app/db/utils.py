from typing import Iterable, List, Optional

from app.core.common import api_row, parse_id
from app.db.engine import connection


def ids(values: Iterable) -> list:
    """UUIDs for the valid id strings in `values` (invalid ones can't match anything)."""
    return [u for u in (parse_id(v) for v in values) if u is not None]


async def fetch_all(stmt) -> List[dict]:
    async with connection() as conn:
        return [api_row(r) for r in (await conn.execute(stmt)).mappings()]


async def fetch_one(stmt) -> Optional[dict]:
    async with connection() as conn:
        return api_row((await conn.execute(stmt)).mappings().first())


async def scalar(stmt):
    async with connection() as conn:
        return await conn.scalar(stmt)


async def execute(stmt, params=None):
    async with connection() as conn:
        return await conn.execute(stmt, params) if params is not None else await conn.execute(stmt)
