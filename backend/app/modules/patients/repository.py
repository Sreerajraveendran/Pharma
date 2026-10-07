"""Patients and prescriptions (with their lines)."""
from datetime import date
from typing import Dict, Iterable, List, Optional

from sqlalchemy import case, exists, func, insert, select, update

from app.core.common import api_row, parse_id
from app.db.engine import connection
from app.db.tables import patients, prescription_lines, prescriptions
from app.db.utils import execute, fetch_all, fetch_one, ids, scalar

LINE_FIELDS = ["medicine_id", "dosage_instruction", "duration_days", "quantity_prescribed", "dispensed_quantity"]


def _page(stmt, skip: int, limit: int):
    stmt = stmt.offset(skip)
    return stmt.limit(limit) if limit else stmt


# Patients

def _patient_values(data: dict) -> dict:
    values = dict(data)
    if isinstance(values.get("date_of_birth"), str):
        values["date_of_birth"] = date.fromisoformat(values["date_of_birth"])
    return values


async def list_patients(skip: int = 0, limit: int = 0) -> List[dict]:
    return await fetch_all(_page(select(patients).order_by(patients.c.name, patients.c.id), skip, limit))


async def count_patients() -> int:
    return await scalar(select(func.count()).select_from(patients))


async def get_patient(patient_id: str) -> Optional[dict]:
    key = parse_id(patient_id)
    return await fetch_one(select(patients).where(patients.c.id == key)) if key else None


async def patients_by_ids(patient_ids: Iterable[str], fields: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    cols = [patients.c.id] + [patients.c[f] for f in fields if f != "id"] if fields else list(patients.c)
    rows = await fetch_all(select(*cols).where(patients.c.id.in_(ids(patient_ids))))
    return {r["id"]: r for r in rows}


async def insert_patient(data: dict) -> dict:
    async with connection() as conn:
        row = (await conn.execute(insert(patients).values(**_patient_values(data)).returning(*patients.c))).mappings().one()
    return api_row(row)


# Prescriptions

async def _with_lines(headers: List[dict]) -> List[dict]:
    """Attaches each prescription's lines as `medicines` (one query for all of them)."""
    if not headers:
        return headers
    stmt = (select(prescription_lines.c.prescription_id, *[prescription_lines.c[f] for f in LINE_FIELDS])
            .where(prescription_lines.c.prescription_id.in_(ids(h["id"] for h in headers)))
            .order_by(prescription_lines.c.prescription_id, prescription_lines.c.position))
    by_rx: Dict[str, list] = {}
    for line in await fetch_all(stmt):
        by_rx.setdefault(line.pop("prescription_id"), []).append(line)
    for h in headers:
        h["medicines"] = by_rx.get(h["id"], [])
    return headers


def _rx_filter(stmt, patient_id: Optional[str]):
    return stmt.where(prescriptions.c.patient_id == parse_id(patient_id)) if patient_id else stmt


async def list_prescriptions(patient_id: Optional[str] = None, skip: int = 0, limit: int = 0) -> List[dict]:
    if patient_id and parse_id(patient_id) is None:
        return []
    stmt = _rx_filter(select(prescriptions), patient_id).order_by(prescriptions.c.date_issued.desc(), prescriptions.c.id)
    return await _with_lines(await fetch_all(_page(stmt, skip, limit)))


async def count_prescriptions(patient_id: Optional[str] = None) -> int:
    return await scalar(_rx_filter(select(func.count()).select_from(prescriptions), patient_id))


async def count_prescriptions_with_dispensing() -> int:
    dispensed = exists().where(prescription_lines.c.prescription_id == prescriptions.c.id,
                               prescription_lines.c.dispensed_quantity > 0)
    return await scalar(select(func.count()).select_from(prescriptions).where(dispensed))


async def get_prescription(rx_id: str, lock: bool = False) -> Optional[dict]:
    """lock=True takes a row lock on the prescription for the current transaction."""
    key = parse_id(rx_id)
    if key is None:
        return None
    stmt = select(prescriptions).where(prescriptions.c.id == key)
    row = await fetch_one(stmt.with_for_update() if lock else stmt)
    return (await _with_lines([row]))[0] if row else None


async def insert_prescription(data: dict) -> dict:
    lines = data.get("medicines", [])
    header = {k: v for k, v in data.items() if k != "medicines"}
    header["patient_id"] = parse_id(header["patient_id"])
    async with connection() as conn:
        row = api_row((await conn.execute(insert(prescriptions).values(**header).returning(*prescriptions.c))).mappings().one())
        if lines:
            await conn.execute(insert(prescription_lines), [
                {"prescription_id": parse_id(row["id"]), "position": i,
                 **{f: line.get(f, 0) for f in LINE_FIELDS}, "medicine_id": parse_id(line["medicine_id"])}
                for i, line in enumerate(lines)])
    row["medicines"] = [{f: (line.get(f, 0) if f != "medicine_id" else line["medicine_id"]) for f in LINE_FIELDS}
                        for line in lines]
    return row


async def adjust_dispensed(rx_id: str, medicine_id: str, quantity: int):
    """Adds (or with a negative quantity, removes) dispensed units on one prescription line.
    The database refuses to go below zero or above the prescribed quantity."""
    await execute(update(prescription_lines)
                  .where(prescription_lines.c.prescription_id == parse_id(rx_id),
                         prescription_lines.c.medicine_id == parse_id(medicine_id))
                  .values(dispensed_quantity=prescription_lines.c.dispensed_quantity + quantity))


async def refresh_prescription_status(rx_id: str):
    """Fully Dispensed once every line reached its prescribed quantity, otherwise Active."""
    key = parse_id(rx_id)
    pending = exists().where(prescription_lines.c.prescription_id == key,
                             prescription_lines.c.dispensed_quantity < prescription_lines.c.quantity_prescribed)
    await execute(update(prescriptions).where(prescriptions.c.id == key)
                  .values(status=case((pending, "Active"), else_="Fully Dispensed")))
