"""Invoices: storage, filtering, numbering and analytics (computed in SQL).

Invoices are exposed with their human number as `id` ("INV-100001"); the UUID primary key
stays internal. Line items, refunds and the audit trail live in child tables and are
assembled into the API shape here.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Dict, Iterable, List, Optional

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy import delete as sql_delete, insert as sql_insert, update as sql_update
from sqlalchemy.sql import ColumnElement

from app.core.common import api_value, parse_id, utc
from app.db.engine import connection, streaming_connection
from app.db.tables import invoice_events, invoice_items, invoice_number_seq, invoice_refunds, invoices

CANCELLED = "Cancelled"
WALK_IN = "Walk-in Customer"

# Domain filter keys -> columns
EQUALITY_FIELDS = {
    "bill_type": invoices.c.bill_type, "payment_method": invoices.c.payment_method, "status": invoices.c.status,
    "cashier": invoices.c.cashier_name, "store": invoices.c.store_name, "doctor": invoices.c.doctor_name,
    "patient_type": invoices.c.patient_type, "insurance_provider": invoices.c.insurance_details["provider"].astext,
}
# API sort keys -> columns
SORT_COLUMNS = {
    "date": invoices.c.date, "id": invoices.c.number, "patient_name": invoices.c.patient_name,
    "gross_amount": invoices.c.gross_amount, "net_payable": invoices.c.net_payable,
    "amount_paid": invoices.c.amount_paid, "balance_due": invoices.c.balance_due, "status": invoices.c.status,
    "bill_type": invoices.c.bill_type, "payment_method": invoices.c.payment_method,
}
# Distinct-value fields for the Reports dropdowns
DISTINCT_COLUMNS = {
    "bill_type": invoices.c.bill_type, "payment_method": invoices.c.payment_method, "status": invoices.c.status,
    "cashier_name": invoices.c.cashier_name, "store_name": invoices.c.store_name,
    "doctor_name": invoices.c.doctor_name, "insurance_details.provider": invoices.c.insurance_details["provider"].astext,
}
HEADER_FIELDS = ["date", "patient_name", "patient_phone", "patient_type", "doctor_name", "bill_type",
                 "payment_method", "cashier_name", "store_name", "gross_amount", "discount_applied", "net_payable",
                 "amount_paid", "balance_due", "refunded_amount", "status", "stock_deducted", "duplicated_from",
                 "cancelled_at", "cancelled_by", "amount_paid_before_cancel", "qr_code", "barcode", "insurance_details"]
ITEM_FIELDS = ["name", "medicine_id", "batch_id", "batch_number", "quantity", "unit_price", "discount", "gst",
               "total_price", "credited_to_prescription"]


@dataclass
class InvoiceFilter:
    """Database-independent invoice filter. `end` is exclusive unless end_inclusive."""
    search: str = ""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    end_inclusive: bool = False
    equals: Dict[str, str] = field(default_factory=dict)  # keys from EQUALITY_FIELDS
    exclude_cancelled: bool = False


# Invoice numbers

def invoice_code(number: int) -> str:
    return f"INV-{number}"


def parse_code(code: str) -> Optional[int]:
    if isinstance(code, str) and code.startswith("INV-") and code[4:].isdigit():
        return int(code[4:])
    return None


async def next_number() -> str:
    """Reserves the next invoice number (from the invoice_number_seq sequence)."""
    async with connection() as conn:
        return invoice_code(await conn.scalar(select(invoice_number_seq.next_value())))


# Filtering

def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _not_cancelled() -> ColumnElement:
    return invoices.c.status != CANCELLED


def _where(f: InvoiceFilter) -> List[ColumnElement]:
    conditions: List[ColumnElement] = []
    term = f.search.strip()
    if term:
        # User text is matched literally (LIKE wildcards escaped), case-insensitively
        pattern = f"%{_escape_like(term)}%"
        conditions.append(or_(
            func.concat("INV-", invoices.c.number).ilike(pattern, escape="\\"),
            invoices.c.patient_name.ilike(pattern, escape="\\"),
            invoices.c.patient_phone.ilike(pattern, escape="\\"),
            invoices.c.doctor_name.ilike(pattern, escape="\\"),
            invoices.c.cashier_name.ilike(pattern, escape="\\"),
            exists().where(invoice_items.c.invoice_id == invoices.c.id,
                           invoice_items.c.name.ilike(pattern, escape="\\")),
        ))
    if f.start:
        conditions.append(invoices.c.date >= f.start)
    if f.end:
        conditions.append(invoices.c.date <= f.end if f.end_inclusive else invoices.c.date < f.end)
    for key, value in f.equals.items():
        if value:
            conditions.append(EQUALITY_FIELDS[key] == value)
    if f.exclude_cancelled:
        conditions.append(_not_cancelled())
    return conditions


# Row -> API shape

def _tax(row) -> dict:
    return {"cgst": api_value(row["cgst"]), "sgst": api_value(row["sgst"]), "igst": api_value(row["igst"]),
            "total_gst": api_value(row["total_gst"]), "inclusive": row["gst_inclusive"]}


def _ledger(row) -> dict:
    return {
        "id": invoice_code(row["number"]), "date": row["date"], "patient_id": api_value(row["patient_id"]),
        "patient_name": row["patient_name"], "bill_type": row["bill_type"], "payment_method": row["payment_method"],
        "gross_amount": api_value(row["gross_amount"]), "discount_applied": api_value(row["discount_applied"]),
        "tax_breakdown": _tax(row), "net_payable": api_value(row["net_payable"]),
        "amount_paid": api_value(row["amount_paid"]), "balance_due": api_value(row["balance_due"]),
        "refunded_amount": api_value(row["refunded_amount"]), "status": row["status"],
        "cashier_name": row["cashier_name"], "store_name": row["store_name"],
    }


LEDGER_COLUMNS = [invoices.c[c] for c in (
    "number", "date", "patient_id", "patient_name", "bill_type", "payment_method", "gross_amount",
    "discount_applied", "net_payable", "amount_paid", "balance_due", "refunded_amount", "status",
    "cashier_name", "store_name", "cgst", "sgst", "igst", "total_gst", "gst_inclusive")]


async def _assemble(conn, row) -> dict:
    """A full invoice in the API shape: header plus items, refunds and audit trail."""
    key = row["id"]
    items = (await conn.execute(select(*[invoice_items.c[f] for f in ITEM_FIELDS])
                                .where(invoice_items.c.invoice_id == key)
                                .order_by(invoice_items.c.position))).mappings().all()
    refunds = (await conn.execute(select(invoice_refunds).where(invoice_refunds.c.invoice_id == key)
                                  .order_by(invoice_refunds.c.refunded_at, invoice_refunds.c.id))).mappings().all()
    events = (await conn.execute(select(invoice_events).where(invoice_events.c.invoice_id == key)
                                 .order_by(invoice_events.c.at, invoice_events.c.id))).mappings().all()

    inv = {f: api_value(row[f]) for f in HEADER_FIELDS}
    inv.update({
        "id": invoice_code(row["number"]),
        "patient_id": api_value(row["patient_id"]),
        "prescription_id": api_value(row["prescription_id"]),
        "tax_breakdown": _tax(row),
        "billing_items": [{k: api_value(v) for k, v in dict(i).items()} for i in items],
        "refunds": [{"refund_amount": api_value(r["amount"]), "reason": r["reason"],
                     "approved_by": r["approved_by"], "refund_date": r["refunded_at"].isoformat()} for r in refunds],
        "audit_trail": [{"user": e["user_name"], "timestamp": e["at"].isoformat(), "action_type": e["action_type"],
                         "previous_value": e["previous_value"], "new_value": e["new_value"]} for e in events],
    })
    inv["refund_details"] = ({**inv["refunds"][-1], "refund_amount": inv["refunded_amount"]}
                             if inv["refunds"] else {})
    return inv


def _key_condition(invoice_id: str) -> Optional[ColumnElement]:
    number = parse_code(invoice_id)
    if number is not None:
        return invoices.c.number == number
    key = parse_id(invoice_id)
    return invoices.c.id == key if key else None


# Reads

async def count(f: InvoiceFilter) -> int:
    async with connection() as conn:
        return await conn.scalar(select(func.count()).select_from(invoices).where(*_where(f)))


async def find_page(f: InvoiceFilter, sort_by: str, ascending: bool, skip: int, limit: int) -> List[dict]:
    column = SORT_COLUMNS[sort_by]
    order = [column.asc(), invoices.c.number.asc()] if ascending else [column.desc(), invoices.c.number.desc()]
    stmt = select(*LEDGER_COLUMNS).where(*_where(f)).order_by(*order).offset(skip).limit(limit)
    async with connection() as conn:
        return [_ledger(r) for r in (await conn.execute(stmt)).mappings()]


async def iterate(f: InvoiceFilter) -> AsyncIterator[dict]:
    """Streams matching ledger rows, newest first, through a server-side cursor."""
    stmt = select(*LEDGER_COLUMNS).where(*_where(f)).order_by(invoices.c.date.desc(), invoices.c.number.desc())
    async with streaming_connection() as conn:
        result = await conn.stream(stmt.execution_options(yield_per=500))
        async for row in result.mappings():
            yield _ledger(row)


async def find_all(f: InvoiceFilter) -> List[dict]:
    """Matching invoices with the fields the KPI reference calculation reads."""
    stmt = select(*LEDGER_COLUMNS, invoices.c.insurance_details).where(*_where(f))
    async with connection() as conn:
        return [{**_ledger(r), "insurance_details": r["insurance_details"]} for r in (await conn.execute(stmt)).mappings()]


async def summary_totals(f: InvoiceFilter) -> dict:
    """Totals over every matching invoice; cancelled ones are excluded from the sums."""
    nc = _not_cancelled()

    def billed(column):
        return func.coalesce(func.sum(column).filter(nc), 0)

    stmt = select(
        billed(invoices.c.gross_amount).label("gross_total"),
        billed(invoices.c.discount_applied).label("discount_total"),
        billed(invoices.c.total_gst).label("gst_total"),
        billed(invoices.c.net_payable).label("net_total"),
        billed(invoices.c.amount_paid).label("paid_total"),
        billed(invoices.c.refunded_amount).label("refund_total"),
        billed(invoices.c.balance_due).label("due_total"),
        func.count().filter(~nc).label("cancelled_count"),
    ).select_from(invoices).where(*_where(f))
    async with connection() as conn:
        row = (await conn.execute(stmt)).mappings().one()
    return {k: api_value(v) for k, v in row.items()}


async def get(invoice_id: str, lock: bool = False) -> Optional[dict]:
    """By invoice number ("INV-n") or UUID. lock=True takes a row lock for the current transaction."""
    condition = _key_condition(invoice_id)
    if condition is None:
        return None
    stmt = select(invoices).where(condition)
    async with connection() as conn:
        row = (await conn.execute(stmt.with_for_update() if lock else stmt)).mappings().first()
        return await _assemble(conn, row) if row else None


async def distinct(field_name: str) -> List[str]:
    column = DISTINCT_COLUMNS[field_name]
    async with connection() as conn:
        values = (await conn.execute(select(column).distinct().where(column.is_not(None)))).scalars().all()
    return sorted(v for v in values if isinstance(v, str) and v.strip())


# Writes

def _event_row(invoice_key, event: dict) -> dict:
    return {"invoice_id": invoice_key, "user_name": event["user"], "at": utc(event["timestamp"]),
            "action_type": event["action_type"], "previous_value": event.get("previous_value", ""),
            "new_value": event.get("new_value", "")}


async def insert(doc: dict) -> dict:
    """Stores a complete invoice (header, items, audit trail). doc["id"] comes from next_number()."""
    tax = doc["tax_breakdown"]
    header = {f: doc.get(f) for f in HEADER_FIELDS if doc.get(f) is not None}
    header.update({
        "number": parse_code(doc["id"]),
        "patient_id": parse_id(doc.get("patient_id")),
        "prescription_id": parse_id(doc.get("prescription_id")),
        "cgst": tax["cgst"], "sgst": tax["sgst"], "igst": tax.get("igst", 0.0), "total_gst": tax["total_gst"],
        "gst_inclusive": bool(tax.get("inclusive")),
        "insurance_details": doc.get("insurance_details") or {},
    })
    async with connection() as conn:
        key = await conn.scalar(sql_insert(invoices).values(**header).returning(invoices.c.id))
        items = doc.get("billing_items") or []
        if items:
            await conn.execute(sql_insert(invoice_items), [
                {"invoice_id": key, "position": i, "name": item["name"],
                 "medicine_id": parse_id(item.get("medicine_id")), "batch_id": parse_id(item.get("batch_id")),
                 "batch_number": item.get("batch_number") or "", "quantity": item["quantity"],
                 "unit_price": item["unit_price"], "discount": item.get("discount", 0.0), "gst": item.get("gst", 0.0),
                 "total_price": item["total_price"], "credited_to_prescription": item.get("credited_to_prescription", 0)}
                for i, item in enumerate(items)])
        events = doc.get("audit_trail") or []
        if events:
            await conn.execute(sql_insert(invoice_events), [_event_row(key, e) for e in events])
        row = (await conn.execute(select(invoices).where(invoices.c.id == key))).mappings().one()
        return await _assemble(conn, row)


async def update(invoice_number: str, fields: dict, events: Iterable[dict] = (), refunds: Iterable[dict] = ()) -> dict:
    """Updates header fields and appends audit events/refunds; call inside a transaction
    after get(..., lock=True)."""
    condition = _key_condition(invoice_number)
    async with connection() as conn:
        key = await conn.scalar(sql_update(invoices).where(condition).values(**fields).returning(invoices.c.id))
        events, refunds = list(events), list(refunds)
        if events:
            await conn.execute(sql_insert(invoice_events), [_event_row(key, e) for e in events])
        if refunds:
            await conn.execute(sql_insert(invoice_refunds), [
                {"invoice_id": key, "amount": r["refund_amount"], "reason": r["reason"],
                 "approved_by": r["approved_by"], "refunded_at": utc(r["refund_date"])} for r in refunds])
        row = (await conn.execute(select(invoices).where(invoices.c.id == key))).mappings().one()
        return await _assemble(conn, row)


async def delete(invoice_number: str) -> bool:
    condition = _key_condition(invoice_number)
    if condition is None:
        return False
    async with connection() as conn:
        res = await conn.execute(sql_delete(invoices).where(condition))
    return res.rowcount > 0


# Analytics (SQL)

METRIC_KEYS = ["total_revenue", "net_revenue", "gross_sales", "total_discounts", "gst_collected",
               "total_refunds", "insurance_receivables", "pending_payments", "cash_collection",
               "card_collection", "upi_collection", "avg_bill_value", "num_transactions",
               "prescriptions_billed", "insurance_bills"]


def _metric_columns() -> list:
    """The KPI aggregates (mirrors billing.service.compute_metrics, which tests use as the reference)."""
    nc = _not_cancelled()
    kept = invoices.c.amount_paid - invoices.c.refunded_amount
    insured = or_(invoices.c.bill_type == "Insurance Claim", invoices.c.payment_method == "Insurance")

    def total(expr, *conds):
        return func.coalesce(func.sum(expr).filter(and_(nc, *conds)), 0)

    return [
        total(kept).label("total_revenue"),
        total(invoices.c.gross_amount).label("gross_sales"),
        total(invoices.c.discount_applied).label("total_discounts"),
        total(invoices.c.total_gst).label("gst_collected"),
        total(invoices.c.refunded_amount).label("total_refunds"),
        total(invoices.c.balance_due).label("pending_payments"),
        total(invoices.c.net_payable).label("net_billed"),
        total(kept, invoices.c.payment_method == "Cash").label("cash_collection"),
        total(kept, invoices.c.payment_method == "Card").label("card_collection"),
        total(kept, invoices.c.payment_method == "UPI").label("upi_collection"),
        total(invoices.c.insurance_details["pending_amount"].astext.cast(invoices.c.gross_amount.type),
              insured).label("insurance_receivables"),
        func.count().filter(and_(nc, insured)).label("insurance_bills"),
        func.count().filter(and_(nc, invoices.c.bill_type == "Prescription Sale")).label("prescriptions_billed"),
        func.count().filter(nc).label("num_transactions"),
    ]


def _finish_metrics(row) -> Dict[str, float]:
    m = {k: float(row[k] or 0) for k in row.keys() if k != "bucket"}
    net_billed = m.pop("net_billed")
    m["net_revenue"] = net_billed - m["total_refunds"]
    m["avg_bill_value"] = net_billed / m["num_transactions"] if m["num_transactions"] else 0.0
    return {k: round(m[k], 2) for k in METRIC_KEYS}


async def metrics(f: InvoiceFilter) -> Dict[str, float]:
    async with connection() as conn:
        row = (await conn.execute(select(*_metric_columns()).select_from(invoices).where(*_where(f)))).mappings().one()
    return _finish_metrics(row)


async def metrics_by_bucket(f: InvoiceFilter, start: datetime, end: datetime, buckets: int) -> List[Dict[str, float]]:
    """The metrics for each of `buckets` equal time slices of [start, end) (sparklines)."""
    width = (end - start).total_seconds() / buckets
    index = func.least(func.greatest(
        func.floor(func.extract("epoch", invoices.c.date - start) / width), 0), buckets - 1).label("bucket")
    stmt = select(index, *_metric_columns()).select_from(invoices).where(*_where(f)).group_by(index)
    async with connection() as conn:
        rows = {int(r["bucket"]): _finish_metrics(r) for r in (await conn.execute(stmt)).mappings()}
    empty = {k: 0.0 for k in METRIC_KEYS}
    return [rows.get(i, empty) for i in range(buckets)]


async def revenue_trend(f: InvoiceFilter, tz_offset_minutes: int, monthly: bool) -> Dict[str, Dict[str, float]]:
    """{local day or month 'YYYY-MM-DD'/'YYYY-MM': {revenue, gst}} for non-cancelled invoices."""
    local = func.timezone(func.make_interval(0, 0, 0, 0, 0, tz_offset_minutes), invoices.c.date)
    bucket = func.date_trunc("month" if monthly else "day", local).label("bucket")
    stmt = (select(bucket,
                   func.sum(invoices.c.amount_paid - invoices.c.refunded_amount).label("revenue"),
                   func.sum(invoices.c.total_gst).label("gst"))
            .where(*_where(f), _not_cancelled()).group_by(bucket))
    async with connection() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    fmt = "%Y-%m" if monthly else "%Y-%m-%d"
    return {r["bucket"].strftime(fmt): {"revenue": float(r["revenue"]), "gst": float(r["gst"])} for r in rows}


async def totals_by(f: InvoiceFilter, dimension: str, top: Optional[int] = None) -> List[dict]:
    """Chart series: [{name, value}] grouped by a dimension, largest first."""
    kept = invoices.c.amount_paid - invoices.c.refunded_amount
    insured = or_(invoices.c.bill_type == "Insurance Claim", invoices.c.payment_method == "Insurance")
    if dimension == "payment_method":
        name, value, extra = func.coalesce(invoices.c.payment_method, "Other"), func.sum(kept), []
    elif dimension == "store":
        name, value, extra = func.coalesce(invoices.c.store_name, "Unknown"), func.sum(kept), []
    elif dimension == "customer":
        name, value, extra = invoices.c.patient_name, func.sum(kept), [invoices.c.patient_name != WALK_IN]
    elif dimension == "insurance":
        name = func.coalesce(invoices.c.insurance_details["provider"].astext, "Unknown")
        value = func.sum(func.coalesce(
            invoices.c.insurance_details["approved_amount"].astext.cast(invoices.c.gross_amount.type), 0))
        extra = [insured]
    elif dimension == "medicine":
        name, value, extra = invoice_items.c.name, func.sum(invoice_items.c.quantity), []
    else:
        raise ValueError(dimension)
    stmt = select(name.label("name"), value.label("value"))
    stmt = (stmt.select_from(invoices.join(invoice_items, invoice_items.c.invoice_id == invoices.c.id))
            if dimension == "medicine" else stmt.select_from(invoices))
    stmt = stmt.where(*_where(f), _not_cancelled(), *extra).group_by(name).order_by(value.desc(), name)
    if top:
        stmt = stmt.limit(top)
    async with connection() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [{"name": r["name"], "value": round(float(r["value"]), 2)} for r in rows]


async def first_date(f: InvoiceFilter) -> Optional[datetime]:
    """The earliest invoice date matching the filter (the start of an open-ended period)."""
    async with connection() as conn:
        return await conn.scalar(select(func.min(invoices.c.date)).where(*_where(f)))
