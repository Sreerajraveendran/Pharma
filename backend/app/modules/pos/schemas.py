from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime

class CartItem(BaseModel):
    medicine_id: Optional[str] = None  # informational; the batch determines the medicine
    batch_id: str
    quantity: int = Field(gt=0, le=10000)
    unit_mrp: Optional[float] = None  # ignored: the price always comes from the batch

class CheckoutRequest(BaseModel):
    patient_id: Optional[str] = None
    prescription_id: Optional[str] = None
    items: List[CartItem] = Field(min_length=1, max_length=100)
    payment_method: Literal["Cash", "Card", "UPI"] = "Cash"
    discount_percent: float = Field(default=0.0, ge=0, le=100)

class ReceiptLine(BaseModel):
    name: str
    batch_number: str
    quantity: int
    unit_price: float
    discount: float
    total_price: float

class CheckoutResponse(BaseModel):
    transaction_id: str
    invoice_id: str
    success: bool
    total_amount: float
    discount_applied: float
    net_amount: float
    gst_included: float
    items: List[ReceiptLine]
    message: str

class AuditLogRead(BaseModel):
    id: str
    timestamp: datetime
    batch_id: str
    action_type: str # Sale, Return, Adjustment, Restock
    quantity_changed: int
    patient_id: Optional[str] = None
    notes: str
    medicine_name: Optional[str] = None
    batch_number: Optional[str] = None
