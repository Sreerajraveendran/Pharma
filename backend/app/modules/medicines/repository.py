"""Categories, medicines and stock batches."""
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func, insert, select, update

from app.core.common import api_row, api_value, parse_id
from app.db.engine import connection
from app.db.tables import batches, categories, medicines
from app.db.utils import execute, fetch_all, fetch_one, ids, scalar


def _page(stmt, skip: int, limit: int):
    stmt = stmt.offset(skip)
    return stmt.limit(limit) if limit else stmt


async def _insert(table, data: dict) -> dict:
    async with connection() as conn:
        row = (await conn.execute(insert(table).values(**data).returning(*table.c))).mappings().one()
    return api_row(row)


def _columns(table, fields: Optional[Iterable[str]]):
    return [table.c.id] + [table.c[f] for f in fields if f != "id"] if fields else list(table.c)


# Categories

async def list_categories() -> List[dict]:
    return await fetch_all(select(categories).order_by(categories.c.name))


async def get_category(category_id: str) -> Optional[dict]:
    key = parse_id(category_id)
    return await fetch_one(select(categories).where(categories.c.id == key)) if key else None


async def categories_by_ids(category_ids: Iterable[str]) -> Dict[str, dict]:
    rows = await fetch_all(select(categories).where(categories.c.id.in_(ids(category_ids))))
    return {r["id"]: r for r in rows}


async def insert_category(data: dict) -> dict:
    return await _insert(categories, data)


# Medicines

async def list_medicines(skip: int = 0, limit: int = 0) -> List[dict]:
    return await fetch_all(_page(select(medicines).order_by(medicines.c.name, medicines.c.id), skip, limit))


async def count_medicines() -> int:
    return await scalar(select(func.count()).select_from(medicines))


async def get_medicine(medicine_id: str) -> Optional[dict]:
    key = parse_id(medicine_id)
    return await fetch_one(select(medicines).where(medicines.c.id == key)) if key else None


async def medicines_by_ids(medicine_ids: Iterable[str], fields: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    rows = await fetch_all(select(*_columns(medicines, fields)).where(medicines.c.id.in_(ids(medicine_ids))))
    return {r["id"]: r for r in rows}


async def insert_medicine(data: dict) -> dict:
    return await _insert(medicines, {**data, "category_id": parse_id(data["category_id"])})


# Batches

def _batch_filter(stmt, medicine_ids: Optional[Iterable[str]]):
    return stmt.where(batches.c.medicine_id.in_(ids(medicine_ids))) if medicine_ids is not None else stmt


async def list_batches(medicine_ids: Optional[Iterable[str]] = None, skip: int = 0, limit: int = 0) -> List[dict]:
    stmt = _batch_filter(select(batches), medicine_ids).order_by(batches.c.expiry_date, batches.c.id)
    return await fetch_all(_page(stmt, skip, limit))


async def count_batches(medicine_ids: Optional[Iterable[str]] = None) -> int:
    return await scalar(_batch_filter(select(func.count()).select_from(batches), medicine_ids))


async def batches_by_ids(batch_ids: Iterable[str], lock: bool = False) -> Dict[str, dict]:
    """Batches by id. lock=True takes row locks (SELECT ... FOR UPDATE) for the current transaction."""
    stmt = select(batches).where(batches.c.id.in_(ids(batch_ids))).order_by(batches.c.id)
    rows = await fetch_all(stmt.with_for_update() if lock else stmt)
    return {r["id"]: r for r in rows}


async def insert_batch(data: dict) -> dict:
    return await _insert(batches, {**data, "medicine_id": parse_id(data["medicine_id"])})


async def stock_by_medicine(medicine_ids: Iterable[str]) -> Dict[str, dict]:
    """{medicine_id: {"total": units on hand, "expiries": [expiry dates of its batches]}}"""
    stmt = (select(batches.c.medicine_id, func.sum(batches.c.quantity_on_hand).label("total"),
                   func.array_agg(batches.c.expiry_date).label("expiries"))
            .where(batches.c.medicine_id.in_(ids(medicine_ids)))
            .group_by(batches.c.medicine_id))
    async with connection() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return {str(r["medicine_id"]): {"total": int(r["total"]), "expiries": list(r["expiries"])} for r in rows}


async def stock_value_by_medicine() -> Dict[str, float]:
    """{medicine_id: MRP x quantity on hand across its batches}"""
    stmt = (select(batches.c.medicine_id, func.sum(batches.c.mrp * batches.c.quantity_on_hand).label("value"))
            .group_by(batches.c.medicine_id))
    async with connection() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return {str(r["medicine_id"]): api_value(r["value"]) for r in rows}


async def deduct_stock(batch_id: str, quantity: int) -> bool:
    """Takes `quantity` off a batch only if that much is on hand (atomic)."""
    res = await execute(update(batches)
                        .where(batches.c.id == parse_id(batch_id), batches.c.quantity_on_hand >= quantity)
                        .values(quantity_on_hand=batches.c.quantity_on_hand - quantity))
    return res.rowcount == 1


async def restock(batch_id: str, quantity: int):
    await execute(update(batches).where(batches.c.id == parse_id(batch_id))
                  .values(quantity_on_hand=batches.c.quantity_on_hand + quantity))
