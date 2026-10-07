from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.modules.auth.dependencies import require_pharmacist
from app.core.pagination import page_params
from app.modules.patients import schemas, service

router = APIRouter()


# Patients
@router.get("/patients", response_model=List[schemas.PatientRead])
async def read_patients(response: Response, page: tuple = Depends(page_params)):
    skip, limit = page
    if limit:
        response.headers["X-Total-Count"] = str(await service.count_patients())
    return await service.get_all_patients(skip, limit)

@router.get("/patients/{patient_id}", response_model=schemas.PatientRead)
async def read_patient(patient_id: str):
    patient = await service.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@router.post("/patients", response_model=schemas.PatientRead, status_code=status.HTTP_201_CREATED)
async def create_new_patient(patient: schemas.PatientCreate):
    return await service.create_patient(patient.model_dump())

# Prescriptions
@router.get("/prescriptions", response_model=List[schemas.PrescriptionRead])
async def read_prescriptions(response: Response, page: tuple = Depends(page_params)):
    skip, limit = page
    if limit:
        response.headers["X-Total-Count"] = str(await service.count_prescriptions())
    return await service.get_all_prescriptions(skip, limit)

@router.get("/prescriptions/{rx_id}", response_model=schemas.PrescriptionRead)
async def read_prescription(rx_id: str):
    rx = await service.get_prescription(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return rx

@router.get("/patients/{patient_id}/prescriptions", response_model=List[schemas.PrescriptionRead])
async def read_patient_prescriptions(patient_id: str):
    if not await service.get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return await service.get_prescriptions_by_patient(patient_id)

@router.post("/prescriptions", response_model=schemas.PrescriptionRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_pharmacist)])
async def create_new_prescription(prescription: schemas.PrescriptionCreate):
    if not await service.get_patient(prescription.patient_id):
        raise HTTPException(status_code=400, detail="Invalid patient_id")
    med_ids = [m.medicine_id for m in prescription.medicines]
    if len(set(med_ids)) != len(med_ids):
        raise HTTPException(status_code=400, detail="Each medicine can appear only once per prescription")
    missing = await service.missing_medicines(med_ids)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown medicine_id: {missing[0]}")
    data = prescription.model_dump()
    data["status"] = "Active"
    for m in data["medicines"]:
        m["dispensed_quantity"] = 0
    res = await service.create_prescription(data)
    return await service.get_prescription(res["id"])
