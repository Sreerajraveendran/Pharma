from typing import List, Optional

from app.core.common import expiry_status, now_utc, stock_status, utc, worst_expiry_status
from app.modules.medicines import repository as catalog


# Categories

async def get_all_categories() -> List[dict]:
    return await catalog.list_categories()


async def get_category(category_id: str) -> Optional[dict]:
    return await catalog.get_category(category_id)


async def create_category(category_data: dict) -> dict:
    return await catalog.insert_category(category_data)


# Medicines

async def _enrich_medicines(meds: List[dict]) -> List[dict]:
    """Adds category, total stock and stock/expiry status. Three queries for any number of medicines."""
    if not meds:
        return meds
    categories = await catalog.categories_by_ids({m["category_id"] for m in meds})
    stock = await catalog.stock_by_medicine([m["id"] for m in meds])
    now = now_utc()
    for med in meds:
        s = stock.get(med["id"], {"total": 0, "expiries": []})
        med["category"] = categories.get(med["category_id"])
        med["total_stock"] = s["total"]
        med["stock_level_status"] = stock_status(s["total"], med["min_stock_level"])
        med["expiry_status"] = worst_expiry_status(s["expiries"], now)
    return meds


async def get_all_medicines(skip: int = 0, limit: int = 0) -> List[dict]:
    return await _enrich_medicines(await catalog.list_medicines(skip, limit))


async def count_medicines() -> int:
    return await catalog.count_medicines()


async def get_medicine(medicine_id: str) -> Optional[dict]:
    med = await catalog.get_medicine(medicine_id)
    return (await _enrich_medicines([med]))[0] if med else None


async def create_medicine(medicine_data: dict) -> dict:
    return await catalog.insert_medicine(medicine_data)


# Batches

async def _enrich_batches(batches: List[dict]) -> List[dict]:
    """Adds medicine name and expiry status. One extra query for any number of batches."""
    if not batches:
        return batches
    names = await catalog.medicines_by_ids({b["medicine_id"] for b in batches}, fields=["name"])
    now = now_utc()
    for b in batches:
        med = names.get(b["medicine_id"])
        b["medicine_name"] = med["name"] if med else "Unknown Medicine"
        b["expiry_status"] = expiry_status(b["expiry_date"], now)
    return batches


async def get_all_batches(skip: int = 0, limit: int = 0) -> List[dict]:
    return await _enrich_batches(await catalog.list_batches(skip=skip, limit=limit))


async def count_batches() -> int:
    return await catalog.count_batches()


async def get_batches_by_medicine(medicine_id: str) -> List[dict]:
    return await _enrich_batches(await catalog.list_batches(medicine_ids=[medicine_id]))


async def create_batch(batch_data: dict) -> dict:
    batch_data["expiry_date"] = utc(batch_data["expiry_date"])
    return (await _enrich_batches([await catalog.insert_batch(batch_data)]))[0]
