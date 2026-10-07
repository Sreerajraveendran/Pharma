from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class PatientBase(BaseModel):
    name: str
    phone: str
    email: str
    date_of_birth: str
    allergies: List[str] = []

class PatientCreate(PatientBase):
    pass

class PatientRead(PatientBase):
    id: str

class PrescribedMedicineBase(BaseModel):
    medicine_id: str
    dosage_instruction: str
    duration_days: int
    quantity_prescribed: int
    dispensed_quantity: int = 0

class PrescribedMedicineCreate(BaseModel):
    # Dispensed quantity and status are server-managed and not accepted from clients
    medicine_id: str
    dosage_instruction: str = Field(min_length=1, max_length=500)
    duration_days: int = Field(gt=0, le=3650)
    quantity_prescribed: int = Field(gt=0, le=100000)

class PrescribedMedicineRead(PrescribedMedicineBase):
    medicine_name: Optional[str] = None
    dosage: Optional[str] = None

class PrescriptionCreate(BaseModel):
    patient_id: str
    prescribed_by: str = Field(min_length=1, max_length=200)
    medicines: List[PrescribedMedicineCreate] = Field(min_length=1, max_length=50)

class PrescriptionRead(BaseModel):
    id: str
    patient_id: str
    patient_name: Optional[str] = None
    prescribed_by: str
    date_issued: datetime
    status: str
    medicines: List[PrescribedMedicineRead]
