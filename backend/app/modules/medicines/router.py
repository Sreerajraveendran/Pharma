from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.modules.auth.dependencies import require_pharmacist
from app.modules.medicines import schemas, service
from app.core.pagination import page_params

router = APIRouter()


# Categories
@router.get("/categories", response_model=List[schemas.CategoryRead])
async def read_categories():
    return await service.get_all_categories()

@router.post("/categories", response_model=schemas.CategoryRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_pharmacist)])
async def create_new_category(category: schemas.CategoryCreate):
    return await service.create_category(category.model_dump())

# Medicines
@router.get("/medicines", response_model=List[schemas.MedicineRead])
async def read_medicines(response: Response, page: tuple = Depends(page_params)):
    skip, limit = page
    if limit:
        response.headers["X-Total-Count"] = str(await service.count_medicines())
    return await service.get_all_medicines(skip, limit)

@router.get("/medicines/{medicine_id}", response_model=schemas.MedicineRead)
async def read_medicine(medicine_id: str):
    med = await service.get_medicine(medicine_id)
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return med

@router.post("/medicines", response_model=schemas.MedicineRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_pharmacist)])
async def create_new_medicine(medicine: schemas.MedicineCreate):
    if not await service.get_category(medicine.category_id):
        raise HTTPException(status_code=400, detail="Invalid category_id")
    res = await service.create_medicine(medicine.model_dump())
    return await service.get_medicine(res["id"])

# Batches
@router.get("/batches", response_model=List[schemas.BatchRead])
async def read_batches(response: Response, page: tuple = Depends(page_params)):
    skip, limit = page
    if limit:
        response.headers["X-Total-Count"] = str(await service.count_batches())
    return await service.get_all_batches(skip, limit)

@router.get("/medicines/{medicine_id}/batches", response_model=List[schemas.BatchRead])
async def read_batches_for_medicine(medicine_id: str):
    if not await service.get_medicine(medicine_id):
        raise HTTPException(status_code=404, detail="Medicine not found")
    return await service.get_batches_by_medicine(medicine_id)

@router.post("/batches", response_model=schemas.BatchRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_pharmacist)])
async def create_new_batch(batch: schemas.BatchCreate):
    if not await service.get_medicine(batch.medicine_id):
        raise HTTPException(status_code=400, detail="Invalid medicine_id")
    return await service.create_batch(batch.model_dump())
