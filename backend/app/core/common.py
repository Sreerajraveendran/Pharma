"""Small helpers shared across modules (dates, ids, stock and money rules)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

# Expiry thresholds in days, for batches and medicines
EXPIRY_CRITICAL_DAYS = 30
EXPIRY_WARNING_DAYS = 180


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def utc(value) -> Optional[datetime]:
    """An aware UTC datetime from a datetime or ISO 8601 string (naive values are UTC)."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def parse_id(value) -> Optional[uuid.UUID]:
    """The UUID for an id string, or None if it isn't one (so lookups simply find nothing)."""
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def api_value(value):
    """Database value -> API value: UUIDs as strings, NUMERIC as float, dates as YYYY-MM-DD."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [api_value(v) for v in value]
    return value


def api_row(row) -> Optional[dict]:
    """A database row as an API dict (see api_value)."""
    if row is None:
        return None
    return {k: api_value(v) for k, v in dict(row).items()}


def expiry_status(expiry, now: Optional[datetime] = None) -> str:
    days = (utc(expiry) - (now or now_utc())).days
    if days < EXPIRY_CRITICAL_DAYS:
        return "CRITICAL"
    if days < EXPIRY_WARNING_DAYS:
        return "WARNING"
    return "HEALTHY"


def worst_expiry_status(expiries: Iterable, now: Optional[datetime] = None) -> str:
    """CRITICAL if any date is critical, else WARNING if any is, else HEALTHY."""
    now = now or now_utc()
    statuses = {expiry_status(e, now) for e in expiries}
    for status in ("CRITICAL", "WARNING"):
        if status in statuses:
            return status
    return "HEALTHY"


def stock_status(total_stock: int, min_stock_level: int) -> str:
    if total_stock == 0:
        return "OUT_OF_STOCK"
    if total_stock < min_stock_level:
        return "LOW"
    return "OPTIMAL"


def collected(invoice: dict) -> float:
    """Money actually kept on an invoice: collected minus refunded."""
    return invoice.get("amount_paid", 0.0) - invoice.get("refunded_amount", 0.0)


def gst_included_in(amount: float, rate: float) -> float:
    """The GST portion of a GST-inclusive amount (e.g. an MRP price)."""
    return round(amount - amount / (1 + rate), 2)
