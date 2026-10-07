from typing import List

from pydantic import BaseModel


class SalesPoint(BaseModel):
    name: str
    revenue: float
    prescriptions: int


class CategoryPoint(BaseModel):
    name: str
    value: int
    stock_value: float
    color: str


class DashboardMetrics(BaseModel):
    total_revenue: float
    prescriptions_dispensed: int
    active_inventory_value: float
    low_stock_alerts: int
    critical_expiry_alerts: int
    warning_expiry_alerts: int
    sales_chart: List[SalesPoint]
    categories_chart: List[CategoryPoint]
