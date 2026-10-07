"""Stock movement audit log."""
from typing import List

from sqlalchemy import insert, select

from app.core.common import parse_id
from app.db.tables import audit_logs
from app.db.utils import execute, fetch_all


async def insert_logs(entries: List[dict]):
    if entries:
        await execute(insert(audit_logs), [
            {**e, "batch_id": parse_id(e["batch_id"]), "patient_id": parse_id(e.get("patient_id"))}
            for e in entries])


async def recent_logs(limit: int = 50) -> List[dict]:
    return await fetch_all(select(audit_logs).order_by(audit_logs.c.timestamp.desc()).limit(limit))
