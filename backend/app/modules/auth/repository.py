"""Users, sessions and authentication events."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.core.common import api_row, parse_id
from app.db.engine import connection
from app.db.tables import auth_events, sessions, users
from app.db.utils import execute, fetch_all, fetch_one, scalar


class EmailTaken(Exception):
    """A user with this email already exists."""


# Users

async def count_users() -> int:
    return await scalar(select(func.count()).select_from(users))


async def get_user(user_id: str) -> Optional[dict]:
    key = parse_id(user_id)
    return await fetch_one(select(users).where(users.c.id == key)) if key else None


async def get_user_by_email(email: str) -> Optional[dict]:
    return await fetch_one(select(users).where(func.lower(users.c.email) == email.lower()))


async def list_users() -> List[dict]:
    return await fetch_all(select(users).order_by(users.c.email))


async def insert_user(fields: dict) -> dict:
    try:
        async with connection() as conn:
            async with conn.begin_nested():  # a failed insert mustn't abort an enclosing transaction
                row = (await conn.execute(insert(users).values(**fields).returning(*users.c))).mappings().one()
    except IntegrityError as e:
        if "uq_users_email_lower" in str(e.orig):
            raise EmailTaken(fields.get("email")) from None
        raise
    return api_row(row)


async def update_user(user_id: str, fields: dict) -> Optional[dict]:
    key = parse_id(user_id)
    if key is None:
        return None
    async with connection() as conn:
        row = (await conn.execute(update(users).where(users.c.id == key).values(**fields)
                                  .returning(*users.c))).mappings().first()
    return api_row(row)


async def delete_user(user_id: str):
    await execute(delete(users).where(users.c.id == parse_id(user_id)))


async def count_active_admins() -> int:
    return await scalar(select(func.count()).select_from(users)
                        .where(users.c.role == "admin", users.c.is_active.is_(True)))


# Sessions

async def insert_session(fields: dict) -> dict:
    async with connection() as conn:
        row = (await conn.execute(insert(sessions).values(**{**fields, "user_id": parse_id(fields["user_id"])})
                                  .returning(*sessions.c))).mappings().one()
    return api_row(row)


async def get_session_by_token_hash(token_hash: str) -> Optional[dict]:
    return await fetch_one(select(sessions).where(sessions.c.token_hash == token_hash))


async def touch_session(session_id: str, at: datetime):
    await execute(update(sessions).where(sessions.c.id == parse_id(session_id)).values(last_seen_at=at))


async def delete_session(session_id: str):
    await execute(delete(sessions).where(sessions.c.id == parse_id(session_id)))


async def delete_session_by_token_hash(token_hash: str):
    await execute(delete(sessions).where(sessions.c.token_hash == token_hash))


async def delete_user_sessions(user_id: str, except_session_id: Optional[str] = None):
    stmt = delete(sessions).where(sessions.c.user_id == parse_id(user_id))
    if except_session_id is not None:
        stmt = stmt.where(sessions.c.id != parse_id(except_session_id))
    await execute(stmt)


async def delete_expired_sessions(now: datetime) -> int:
    """Removes sessions past their absolute expiry (idle ones go when next looked up)."""
    res = await execute(delete(sessions).where(sessions.c.expires_at <= now))
    return res.rowcount


# Authentication events

async def insert_auth_event(fields: dict):
    await execute(insert(auth_events).values(**{**fields, "user_id": parse_id(fields.get("user_id"))}))
