from typing import Dict, List, Optional

from app.core.common import now_utc, utc
from app.modules.medicines import repository as catalog
from app.modules.patients import repository as people


# Patients

async def get_all_patients(skip: int = 0, limit: int = 0) -> List[dict]:
    return await people.list_patients(skip, limit)


async def count_patients() -> int:
    return await people.count_patients()


async def get_patient(patient_id: str) -> Optional[dict]:
    return await people.get_patient(patient_id)


async def create_patient(patient_data: dict) -> dict:
    return await people.insert_patient(patient_data)


# Prescriptions

async def _enrich_prescriptions(rxs: List[dict]) -> List[dict]:
    """Adds patient and medicine names. Two queries for any number of prescriptions."""
    if not rxs:
        return rxs
    patients = await people.patients_by_ids({rx["patient_id"] for rx in rxs}, fields=["name"])
    meds = await catalog.medicines_by_ids({m["medicine_id"] for rx in rxs for m in rx["medicines"]},
                                          fields=["name", "dosage"])
    for rx in rxs:
        patient = patients.get(rx["patient_id"])
        rx["patient_name"] = patient["name"] if patient else "Unknown Patient"
        rx["medicines"] = [{**m,
                            "medicine_name": meds[m["medicine_id"]]["name"] if m["medicine_id"] in meds else "Unknown Medicine",
                            "dosage": meds[m["medicine_id"]].get("dosage", "") if m["medicine_id"] in meds else ""}
                           for m in rx["medicines"]]
        rx["date_issued"] = utc(rx.get("date_issued"))
    return rxs


async def get_all_prescriptions(skip: int = 0, limit: int = 0) -> List[dict]:
    return await _enrich_prescriptions(await people.list_prescriptions(skip=skip, limit=limit))


async def count_prescriptions() -> int:
    return await people.count_prescriptions()


async def get_prescription(rx_id: str) -> Optional[dict]:
    rx = await people.get_prescription(rx_id)
    return (await _enrich_prescriptions([rx]))[0] if rx else None


async def get_prescriptions_by_patient(patient_id: str) -> List[dict]:
    return await _enrich_prescriptions(await people.list_prescriptions(patient_id=patient_id))


async def missing_medicines(medicine_ids: List[str]) -> List[str]:
    """The ids in `medicine_ids` that don't exist (one query)."""
    found: Dict[str, dict] = await catalog.medicines_by_ids(medicine_ids, fields=["id"])
    return [m for m in medicine_ids if m not in found]


async def create_prescription(rx_data: dict) -> dict:
    rx_data["date_issued"] = now_utc()
    return await people.insert_prescription(rx_data)
