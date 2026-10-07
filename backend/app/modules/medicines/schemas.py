from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timezone

class CategoryBase(BaseModel):
    name: str
    color_code: str

class CategoryCreate(CategoryBase):
    pass

class CategoryRead(CategoryBase):
    id: str

class MedicineBase(BaseModel):
    name: str
    generic_name: str
    form: str
    dosage: str
    category_id: str
    manufacturer: str
    prescription_required: bool
    storage_requirement: str
    side_effects: str
    min_stock_level: int
    base_uom: str

class MedicineCreate(MedicineBase):
    name: str = Field(min_length=1, max_length=200)
    min_stock_level: int = Field(ge=0)

class MedicineRead(MedicineBase):
    id: str
    category: Optional[CategoryRead] = None
    total_stock: int = 0
    expiry_status: str = "HEALTHY" # HEALTHY, WARNING, CRITICAL
    stock_level_status: str = "OPTIMAL" # OPTIMAL, LOW, OUT_OF_STOCK

class BatchBase(BaseModel):
    medicine_id: str
    batch_number: str
    expiry_date: datetime
    quantity_on_hand: int
    supplier_id: Optional[str] = None
    location_code: str
    purchase_price: float
    mrp: float

class BatchCreate(BatchBase):
    batch_number: str = Field(min_length=1, max_length=100)
    quantity_on_hand: int = Field(ge=0)
    purchase_price: float = Field(ge=0)
    mrp: float = Field(gt=0)

    @field_validator("expiry_date")
    @classmethod
    def not_expired(cls, v: datetime) -> datetime:
        aware = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if aware <= datetime.now(timezone.utc):
            raise ValueError("Expiry date must be in the future")
        return v

class BatchRead(BatchBase):
    id: str
    medicine_name: Optional[str] = None
    expiry_status: str = "HEALTHY"
