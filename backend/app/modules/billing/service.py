import asyncio
import csv
import io
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from app.core.common import collected, now_utc, utc
from app.db.engine import transaction
from app.modules.pos import repository as audit
from app.modules.medicines import repository as catalog
from app.modules.patients import repository as people
from app.modules.billing import repository as invoices_repo
from app.modules.billing.repository import CANCELLED, METRIC_KEYS, InvoiceFilter

logger = logging.getLogger("app.modules.billing.service")

GST_RATE = 0.12

# Status rules
REFUNDABLE_STATUSES = {"Paid", "Partially Paid", "Partially Refunded"}
CANCELLABLE_STATUSES = {"Paid", "Pending", "Partially Paid"}

SORTABLE_FIELDS = {"date", "id", "patient_name", "gross_amount", "net_payable", "amount_paid",
                   "balance_due", "status", "bill_type", "payment_method"}


class InvoiceError(Exception):
    """A request that is invalid for the invoice's current state (maps to HTTP 400)."""


def _money(value: float) -> float:
    return round(float(value or 0.0) + 0.0, 2)


# Tax engine

def calculate_invoice_taxes(gross_amount: float, discount_applied: float,
                            gst_rate: float = GST_RATE, inclusive: bool = False) -> dict:
    """GST split equally into CGST and SGST.

    inclusive=True: prices already contain GST (MRP pricing; selling above MRP is not
    allowed), so the tax is extracted from the subtotal. inclusive=False: GST is added on top.
    """
    subtotal = max(0.0, gross_amount - discount_applied)
    if inclusive:
        total_gst = round(subtotal - subtotal / (1 + gst_rate), 2)
    else:
        total_gst = round(subtotal * gst_rate, 2)
    cgst = round(total_gst / 2.0, 2)
    sgst = round(total_gst - cgst, 2)
    return {"cgst": cgst, "sgst": sgst, "igst": 0.0, "total_gst": total_gst, "inclusive": inclusive}


def net_payable_for(gross_amount: float, discount_applied: float, taxes: dict) -> float:
    subtotal = max(0.0, gross_amount - discount_applied)
    return _money(subtotal if taxes.get("inclusive") else subtotal + taxes["total_gst"])


# Filters

def _parse_date_bound(value: Optional[str], is_end: bool) -> Optional[Tuple[datetime, bool]]:
    """(instant, inclusive). A bare YYYY-MM-DD covers that whole UTC day, so an end date
    becomes the next midnight, exclusive. Full ISO timestamps are used as given (inclusive);
    naive ones are treated as UTC."""
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00").replace(" ", "+", 1) if "T" in value else value.strip()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise InvoiceError(f"Invalid date: {value!r}. Use YYYY-MM-DD or an ISO 8601 timestamp.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if len(raw) == 10 and is_end:
        return parsed + timedelta(days=1), False
    return parsed, True


def parse_filters(filters: dict) -> InvoiceFilter:
    start = _parse_date_bound(filters.get("start_date"), False)
    end = _parse_date_bound(filters.get("end_date"), True)
    return InvoiceFilter(
        search=filters.get("search") or "",
        start=start[0] if start else None,
        end=end[0] if end else None,
        end_inclusive=end[1] if end else False,
        equals={k: filters[k] for k in invoices_repo.EQUALITY_FIELDS if filters.get(k)},
    )


def date_range(filters: dict) -> Tuple[Optional[datetime], Optional[datetime]]:
    """The start and end instants a filter covers, for period comparisons and chart axes."""
    f = parse_filters(filters)
    return f.start, f.end


# 1. Ledger

async def list_invoices(filters: dict, page: int = 1, limit: int = 25) -> Dict[str, Any]:
    f = parse_filters(filters)
    sort_by = filters.get("sort_by") or "date"
    if sort_by not in SORTABLE_FIELDS:
        raise InvoiceError(f"Cannot sort by {sort_by!r}")

    total_count, docs, sums = await asyncio.gather(
        invoices_repo.count(f),
        invoices_repo.find_page(f, sort_by, filters.get("sort_order") == "asc", (page - 1) * limit, limit),
        invoices_repo.summary_totals(f),
    )
    return {
        "success": True,
        "data": docs,
        "pagination": {
            "total_records": total_count,
            "current_page": page,
            "limit": limit,
            "total_pages": (total_count + limit - 1) // limit,
        },
        # Cancelled invoices are listed but excluded from every total
        "summary_totals": {
            "gross_total": _money(sums.get("gross_total")),
            "discount_total": _money(sums.get("discount_total")),
            "gst_total": _money(sums.get("gst_total")),
            "net_total": _money(sums.get("net_total")),
            "paid_total": _money(sums.get("paid_total")),
            "refund_total": _money(sums.get("refund_total")),
            "net_collected": _money((sums.get("paid_total") or 0) - (sums.get("refund_total") or 0)),
            "due_total": _money(sums.get("due_total")),
            "cancelled_count": sums.get("cancelled_count", 0),
        },
    }


async def get_invoice(invoice_id: str) -> Optional[dict]:
    return await invoices_repo.get(invoice_id)


# 2. Lifecycle

def _audit(user: str, action: str, previous: str, new: str, at: Optional[datetime] = None) -> dict:
    return {"user": user, "timestamp": (at or now_utc()).isoformat(), "action_type": action,
            "previous_value": previous, "new_value": new}


async def insert_invoice(doc: dict, *, inclusive_tax: bool, paid: bool, actor: str,
                         at: Optional[datetime] = None) -> dict:
    """Completes and stores an invoice. doc needs patient/doctor/bill fields, billing_items,
    gross_amount and discount_applied. `at` backdates it (used only for demo history)."""
    gross = _money(doc["gross_amount"])
    discount = _money(doc["discount_applied"])
    if gross < 0 or discount < 0:
        raise InvoiceError("Amounts cannot be negative.")
    if discount > gross:
        raise InvoiceError("Discount cannot exceed the gross amount.")

    taxes = calculate_invoice_taxes(gross, discount, inclusive=inclusive_tax)
    net = net_payable_for(gross, discount, taxes)
    async with transaction():
        invoice_id = await invoices_repo.next_number()
        return await invoices_repo.insert(_complete(doc, invoice_id, gross, discount, taxes, net, paid, actor, at))


def _complete(doc: dict, invoice_id: str, gross: float, discount: float, taxes: dict, net: float,
              paid: bool, actor: str, at: Optional[datetime]) -> dict:

    doc.update({
        "id": invoice_id,
        "date": at or now_utc(),
        "gross_amount": gross,
        "discount_applied": discount,
        "tax_breakdown": taxes,
        "net_payable": net,
        "amount_paid": net if paid else 0.0,
        "balance_due": 0.0 if paid else net,
        "refunded_amount": 0.0,
        "status": "Paid" if paid else "Pending",
        "qr_code": f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={invoice_id}",
        "barcode": f"8901072{invoice_id.split('-')[-1].zfill(6)[-6:]}",
    })
    doc.setdefault("audit_trail", []).append(_audit(actor, "Create", "", "Invoice Created", at))
    doc["insurance_details"] = doc.get("insurance_details") or {}
    return doc


async def create_invoice(invoice_data: dict, actor: str = "System") -> dict:
    doc = dict(invoice_data)
    doc["cashier_name"] = doc.get("cashier_name") or actor
    doc["stock_deducted"] = False
    return await insert_invoice(doc, inclusive_tax=False, paid=True, actor=actor)


async def cancel_invoice(invoice_id: str, user_name: str, at: Optional[datetime] = None) -> Optional[dict]:
    """Cancels a sale; a POS sale's stock and prescription credit are returned in the same transaction."""
    async with transaction():
        inv = await invoices_repo.get(invoice_id, lock=True)  # serialises concurrent cancels/refunds
        if not inv:
            return None
        status = inv.get("status")
        if inv.get("refunded_amount", 0) > 0:
            raise InvoiceError("An invoice with refunds can't be cancelled. Refund the remaining balance instead.")
        if status not in CANCELLABLE_STATUSES:
            raise InvoiceError(f"A {str(status).lower()} invoice cannot be cancelled.")

        updated = await invoices_repo.update(
            inv["id"],
            {"status": CANCELLED, "amount_paid": 0.0, "balance_due": 0.0, "stock_deducted": False,
             "cancelled_at": at or now_utc(), "cancelled_by": user_name,
             "amount_paid_before_cancel": inv.get("amount_paid", 0.0)},
            events=[_audit(user_name, "Cancel", status, CANCELLED, at)],
        )
        if inv.get("stock_deducted"):
            await _reverse_stock(inv, user_name, at)
        return updated


async def _reverse_stock(inv: dict, user_name: str, at: Optional[datetime] = None):
    """Returns a cancelled POS sale's items to their batches and reverses prescription progress."""
    returned = [item for item in inv.get("billing_items", [])
                if item.get("batch_id") and item.get("quantity", 0) > 0]
    for item in returned:
        await catalog.restock(item["batch_id"], item["quantity"])
    await audit.insert_logs([{
        "timestamp": at or now_utc(), "batch_id": item["batch_id"], "action_type": "Return",
        "quantity_changed": item["quantity"], "patient_id": inv.get("patient_id"),
        "notes": f"Cancelled invoice {inv['id']} by {user_name}",
    } for item in returned])

    rx_id = inv.get("prescription_id")
    credited = [item for item in returned if item.get("credited_to_prescription")]
    if rx_id and credited:
        for item in credited:
            await people.adjust_dispensed(rx_id, item.get("medicine_id"), -item["credited_to_prescription"])
        await people.refresh_prescription_status(rx_id)


async def duplicate_invoice(invoice_id: str, user_name: str) -> Optional[dict]:
    """Creates an unpaid draft copy. It records no payment, so it adds no revenue
    until it is actually paid."""
    inv = await invoices_repo.get(invoice_id)
    if not inv:
        return None
    bill_type = inv.get("bill_type")
    if bill_type in ("Refund", "Return", "Credit Note", "Cancelled Invoice"):
        bill_type = "POS Sale"
    doc = {
        "patient_id": inv.get("patient_id"),
        "patient_name": inv.get("patient_name"),
        "patient_phone": inv.get("patient_phone"),
        "patient_type": inv.get("patient_type"),
        "doctor_name": inv.get("doctor_name"),
        "bill_type": bill_type,
        "payment_method": inv.get("payment_method"),
        "gross_amount": inv.get("gross_amount", 0.0),
        "discount_applied": inv.get("discount_applied", 0.0),
        "billing_items": [{k: v for k, v in item.items() if k not in ("batch_id", "credited_to_prescription")}
                          for item in inv.get("billing_items", [])],
        "cashier_name": user_name,
        "store_name": inv.get("store_name"),
        "stock_deducted": False,
        "duplicated_from": inv.get("id"),
    }
    inclusive = bool((inv.get("tax_breakdown") or {}).get("inclusive"))
    return await insert_invoice(doc, inclusive_tax=inclusive, paid=False, actor=user_name)


async def process_refund(invoice_id: str, refund_amount: float, reason: str, user_name: str,
                         at: Optional[datetime] = None) -> Optional[dict]:
    reason = (reason or "").strip()
    amount = _money(refund_amount)
    async with transaction():
        # The row lock makes concurrent refunds see each other's totals
        inv = await invoices_repo.get(invoice_id, lock=True)
        if not inv:
            return None

        status = inv.get("status")
        if status not in REFUNDABLE_STATUSES:
            raise InvoiceError(f"A {str(status).lower()} invoice cannot be refunded.")
        if not reason:
            raise InvoiceError("A refund reason is required.")

        already = _money(inv.get("refunded_amount", 0.0))
        refundable = _money(inv.get("amount_paid", 0.0) - already)
        if amount <= 0:
            raise InvoiceError("Refund amount must be greater than zero.")
        if amount > refundable:
            raise InvoiceError(f"Refund amount exceeds the refundable balance of ₹{refundable:.2f}.")

        total_refunded = _money(already + amount)
        new_status = "Refunded" if total_refunded >= _money(inv.get("amount_paid", 0.0)) else "Partially Refunded"
        return await invoices_repo.update(
            inv["id"], {"status": new_status, "refunded_amount": total_refunded},
            events=[_audit(user_name, "Refund", status, f"{new_status} (₹{amount:.2f})", at)],
            refunds=[{"refund_amount": amount, "reason": reason, "approved_by": user_name,
                      "refund_date": (at or now_utc()).isoformat()}],
        )


async def delete_invoice(invoice_id: str) -> bool:
    return await invoices_repo.delete(invoice_id)


_FILTER_OPTIONS_TTL = 60.0
_filter_options_cache: Tuple[float, Optional[dict]] = (0.0, None)


async def get_filter_options() -> Dict[str, List[str]]:
    """Distinct values present in the data, for the Reports filter dropdowns (cached 60 s)."""
    global _filter_options_cache
    cached_at, cached = _filter_options_cache
    if cached is not None and time.monotonic() - cached_at < _FILTER_OPTIONS_TTL:
        return cached
    keys = {"bill_types": "bill_type", "payment_methods": "payment_method", "statuses": "status",
            "cashiers": "cashier_name", "stores": "store_name", "doctors": "doctor_name",
            "insurance_providers": "insurance_details.provider"}
    values = await asyncio.gather(*(invoices_repo.distinct(f) for f in keys.values()))
    result = dict(zip(keys, values))
    _filter_options_cache = (time.monotonic(), result)
    return result


# 3. Analytics

def compute_metrics(invoices: List[dict]) -> Dict[str, float]:
    """Reference implementation of the KPI metrics in Python. Reports compute them in SQL
    (invoices_repo.metrics); the tests check that the two agree."""
    m = {k: 0.0 for k in METRIC_KEYS}
    net_billed = 0.0
    for inv in invoices:
        if inv.get("status") == CANCELLED:
            continue
        kept = collected(inv)
        pm = inv.get("payment_method")
        m["total_revenue"] += kept
        m["gross_sales"] += inv.get("gross_amount", 0.0)
        m["total_discounts"] += inv.get("discount_applied", 0.0)
        m["gst_collected"] += (inv.get("tax_breakdown") or {}).get("total_gst", 0.0)
        m["total_refunds"] += inv.get("refunded_amount", 0.0)
        m["pending_payments"] += inv.get("balance_due", 0.0)
        net_billed += inv.get("net_payable", 0.0)
        if pm == "Cash":
            m["cash_collection"] += kept
        elif pm == "Card":
            m["card_collection"] += kept
        elif pm == "UPI":
            m["upi_collection"] += kept
        if inv.get("bill_type") == "Insurance Claim" or pm == "Insurance":
            m["insurance_bills"] += 1
            m["insurance_receivables"] += (inv.get("insurance_details") or {}).get("pending_amount", 0.0)
        if inv.get("bill_type") == "Prescription Sale":
            m["prescriptions_billed"] += 1
        m["num_transactions"] += 1
    # Net revenue: everything billed (paid or not) less refunds
    m["net_revenue"] = net_billed - m["total_refunds"]
    m["avg_bill_value"] = net_billed / m["num_transactions"] if m["num_transactions"] else 0.0
    return {k: round(v, 2) for k, v in m.items()}


KPI_LABELS = {
    "total_revenue": "Total Revenue", "net_revenue": "Net Revenue", "gross_sales": "Gross Sales",
    "total_discounts": "Total Discounts", "gst_collected": "Total GST Collected",
    "total_refunds": "Total Refunds", "insurance_receivables": "Insurance Receivables",
    "pending_payments": "Pending Payments", "cash_collection": "Cash Collection",
    "card_collection": "Card Collection", "upi_collection": "UPI Collection",
    "avg_bill_value": "Average Bill Value", "num_transactions": "Transactions Count",
    "prescriptions_billed": "Total Prescriptions", "insurance_bills": "Total Insurance Bills",
}
COUNT_KPIS = {"num_transactions", "prescriptions_billed", "insurance_bills"}
SPARKLINE_POINTS = 10


async def get_financial_kpis(filters: dict) -> Dict[str, Any]:
    f = parse_filters(filters)
    current = await invoices_repo.metrics(f)

    start, end = f.start, f.end
    if start is None:
        start = await invoices_repo.first_date(f)
    if end is None:
        end = now_utc()

    # Period-over-period: the same-length window immediately before the selected one
    previous = None
    if filters.get("start_date") and start < end:
        span = end - start
        previous = await invoices_repo.metrics(InvoiceFilter(search=f.search, equals=f.equals,
                                                             start=start - span, end=start))

    # Sparklines: the metric across equal slices of the selected period
    if start is not None and start < end:
        bucket_metrics = await invoices_repo.metrics_by_bucket(f, start, end, SPARKLINE_POINTS)
    else:
        bucket_metrics = [dict.fromkeys(METRIC_KEYS, 0.0)] * SPARKLINE_POINTS

    def kpi(key: str) -> dict:
        val = current[key]
        change = None
        if previous is not None and previous[key]:
            change = round((val - previous[key]) / abs(previous[key]) * 100, 1)
        return {
            "value": f"{int(val)}" if key in COUNT_KPIS else f"₹{val:,.2f}",
            "raw": val,
            "change": change,
            "previous": previous[key] if previous is not None else None,
            "sparkline": [bm[key] for bm in bucket_metrics],
            "label": KPI_LABELS[key],
        }

    return {key: kpi(key) for key in METRIC_KEYS}


async def get_financial_charts(filters: dict, tz_offset_minutes: int = 0) -> Dict[str, Any]:
    f = parse_filters(filters)
    local = timezone(timedelta(minutes=tz_offset_minutes))

    # 1. Revenue trend across the selected period, in the viewer's local days
    end = f.end or now_utc()
    start = f.start or (end - timedelta(days=29))
    first_day = start.astimezone(local).date()
    last_day = (end - timedelta(microseconds=1)).astimezone(local).date()
    monthly = (last_day - first_day).days > 92

    def bucket_key(d) -> str:
        return d.strftime("%Y-%m") if monthly else d.isoformat()

    trend: Dict[str, Dict[str, float]] = {}
    day = first_day
    while day <= last_day:
        trend.setdefault(bucket_key(day), {"revenue": 0.0, "gst": 0.0})
        day += timedelta(days=1)

    sums, payment, insurance, medicines, customers, stores = await asyncio.gather(
        invoices_repo.revenue_trend(f, tz_offset_minutes, monthly),
        invoices_repo.totals_by(f, "payment_method"),
        invoices_repo.totals_by(f, "insurance"),
        invoices_repo.totals_by(f, "medicine", top=5),
        invoices_repo.totals_by(f, "customer", top=5),
        invoices_repo.totals_by(f, "store"),
    )
    for key, v in sums.items():
        if key in trend:
            trend[key] = v
    revenue_trend = [{
        "name": datetime.strptime(k, "%Y-%m").strftime("%b %Y") if monthly
        else datetime.strptime(k, "%Y-%m-%d").strftime("%b %d"),
        "revenue": round(v["revenue"], 2),
        "gst": round(v["gst"], 2),
    } for k, v in trend.items()]

    return {
        "revenue_trend": revenue_trend,
        "payment_distribution": payment,
        "insurance_distribution": insurance,
        "top_medicines": medicines,
        "top_customers": customers,
        "sales_by_store": stores,
    }


async def collected_since(start: datetime) -> List[dict]:
    """Non-cancelled invoices from `start`, with the fields revenue figures need."""
    return await invoices_repo.find_all(InvoiceFilter(start=start, exclude_cancelled=True))


# 4. CSV export

CSV_HEADER = ["Invoice ID", "Date", "Customer Name", "Patient ID", "Bill Type", "Payment Method",
              "Gross Amount", "Discount", "GST", "Net Amount", "Amount Paid", "Refunded", "Balance Due",
              "Status", "Cashier", "Store Name"]


def _csv_row(inv: dict) -> list:
    dt = utc(inv.get("date"))
    return [
        inv.get("id"),
        dt.isoformat() if dt else "",
        _csv_safe(inv.get("patient_name")),
        inv.get("patient_id"),
        inv.get("bill_type"),
        inv.get("payment_method"),
        f"{inv.get('gross_amount', 0.0):.2f}",
        f"{inv.get('discount_applied', 0.0):.2f}",
        f"{(inv.get('tax_breakdown') or {}).get('total_gst', 0.0):.2f}",
        f"{inv.get('net_payable', 0.0):.2f}",
        f"{inv.get('amount_paid', 0.0):.2f}",
        f"{inv.get('refunded_amount', 0.0):.2f}",
        f"{inv.get('balance_due', 0.0):.2f}",
        inv.get("status"),
        _csv_safe(inv.get("cashier_name")),
        _csv_safe(inv.get("store_name")),
    ]


def export_invoices_csv(invoices: List[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADER)
    for inv in invoices:
        writer.writerow(_csv_row(inv))
    return output.getvalue()


async def stream_invoices_csv(filters: dict, chunk_rows: int = 500) -> AsyncIterator[str]:
    """CSV of every matching invoice, produced as it is read (constant memory)."""
    f = parse_filters(filters)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADER)
    rows = 0
    async for inv in invoices_repo.iterate(f):
        writer.writerow(_csv_row(inv))
        rows += 1
        if rows % chunk_rows == 0:
            yield output.getvalue()
            output.seek(0)
            output.truncate()
    yield output.getvalue()


def _csv_safe(value):
    # Prevent spreadsheet formula injection from free-text fields
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value
