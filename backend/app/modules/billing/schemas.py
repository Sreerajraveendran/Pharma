from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# Requests

class BillingItemSchema(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0)
    batch_number: str
    unit_price: float = Field(ge=0)
    discount: float = Field(ge=0)
    gst: float = Field(ge=0)
    total_price: float = Field(ge=0)


class InsuranceDetailsSchema(BaseModel):
    provider: str
    policy_number: str
    claim_number: str
    claim_amount: float
    approved_amount: float
    pending_amount: float
    status: str  # Pending, Approved, Settled, Rejected
    settlement_date: Optional[str] = None
    rejection_reason: Optional[str] = None


class InvoiceCreate(BaseModel):
    patient_id: Optional[str] = None
    patient_name: str
    patient_phone: Optional[str] = None
    patient_type: str  # Walk-in, Registered
    doctor_name: str
    bill_type: str
    payment_method: str
    gross_amount: float = Field(ge=0)
    discount_applied: float = Field(ge=0)
    billing_items: List[BillingItemSchema] = Field(min_length=1)
    insurance_details: Optional[InsuranceDetailsSchema] = None
    cashier_name: Optional[str] = None  # defaults to the signed-in user
    store_name: str


# Responses. Invoices keep any additional stored fields (audit trail, refunds, ...).

class InvoiceOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    date: datetime
    status: str
    bill_type: Optional[str] = None
    payment_method: Optional[str] = None
    gross_amount: float = 0.0
    discount_applied: float = 0.0
    net_payable: float = 0.0
    amount_paid: float = 0.0
    balance_due: float = 0.0
    refunded_amount: float = 0.0


class Pagination(BaseModel):
    total_records: int
    current_page: int
    limit: int
    total_pages: int


class SummaryTotals(BaseModel):
    """Totals over every matching invoice, excluding cancelled ones."""
    gross_total: float
    discount_total: float
    gst_total: float
    net_total: float
    paid_total: float
    refund_total: float
    net_collected: float
    due_total: float
    cancelled_count: int


class InvoiceList(BaseModel):
    success: bool
    data: List[InvoiceOut]
    pagination: Pagination
    summary_totals: SummaryTotals


class Kpi(BaseModel):
    value: str
    raw: float
    change: Optional[float] = Field(None, description="% vs the previous period of the same length; null without a start date")
    previous: Optional[float] = None
    sparkline: List[float]
    label: str


class NamedValue(BaseModel):
    name: Optional[str] = None
    value: float


class TrendPoint(BaseModel):
    name: str
    revenue: float
    gst: float


class Charts(BaseModel):
    revenue_trend: List[TrendPoint]
    payment_distribution: List[NamedValue]
    insurance_distribution: List[NamedValue]
    top_medicines: List[NamedValue]
    top_customers: List[NamedValue]
    sales_by_store: List[NamedValue]


class FilterOptions(BaseModel):
    bill_types: List[str]
    payment_methods: List[str]
    statuses: List[str]
    cashiers: List[str]
    stores: List[str]
    doctors: List[str]
    insurance_providers: List[str]


KpiReport = Dict[str, Kpi]
