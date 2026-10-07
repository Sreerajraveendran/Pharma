from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta, timezone
import asyncio
from jinja2 import Template
from starlette.concurrency import run_in_threadpool
from xhtml2pdf import pisa
import io

from app.modules.auth.dependencies import get_current_user, require_pharmacist
from app.modules.billing import schemas, service
from app.modules.billing.invoice_template import INVOICE_HTML
from app.core.common import utc

router = APIRouter()


def invoice_filters(
    search: Optional[str] = Query(None, max_length=100),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (UTC day) or ISO 8601 timestamp"),
    end_date: Optional[str] = Query(None, description="Inclusive. YYYY-MM-DD (UTC day) or ISO 8601 timestamp"),
    bill_type: Optional[str] = Query(None),
    payment_method: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    cashier: Optional[str] = Query(None),
    store: Optional[str] = Query(None),
    doctor: Optional[str] = Query(None),
    insurance_provider: Optional[str] = Query(None),
    patient_type: Optional[str] = Query(None),
) -> dict:
    return {
        "search": search, "start_date": start_date, "end_date": end_date, "bill_type": bill_type,
        "payment_method": payment_method, "status": status, "cashier": cashier, "store": store,
        "doctor": doctor, "insurance_provider": insurance_provider, "patient_type": patient_type,
    }


@router.get("/billing/invoices", response_model=schemas.InvoiceList)
async def get_all_invoices(
    filters: dict = Depends(invoice_filters),
    sort_by: str = Query("date"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=500),
):
    return await service.list_invoices({**filters, "sort_by": sort_by, "sort_order": sort_order}, page, limit)


@router.get("/billing/invoices/filter-options", response_model=schemas.FilterOptions)
async def get_invoice_filter_options():
    return await service.get_filter_options()


@router.get("/billing/invoices/kpis", response_model=schemas.KpiReport)
async def get_billing_kpis(filters: dict = Depends(invoice_filters)):
    return await service.get_financial_kpis(filters)


@router.get("/billing/invoices/charts", response_model=schemas.Charts)
async def get_billing_charts(
    filters: dict = Depends(invoice_filters),
    tz_offset: int = Query(0, ge=-14 * 60, le=14 * 60, description="Viewer's UTC offset in minutes, e.g. 330 for IST"),
):
    return await service.get_financial_charts(filters, tz_offset)


@router.get("/billing/invoices/export/csv")
async def export_invoices_to_csv(filters: dict = Depends(invoice_filters)):
    service.parse_filters(filters)  # reject bad filters before streaming starts
    return StreamingResponse(
        service.stream_invoices_csv(filters),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=billing_reports.csv"},
    )

REPORT_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {
        size: a4 landscape;
        margin: 1cm;
    }
    body {
        font-family: Helvetica, Arial, sans-serif;
        color: #151c27;
        font-size: 8.5pt;
        line-height: 1.3;
    }
    .header-table {
        width: 100%;
        border-bottom: 2px solid #003d9b;
        margin-bottom: 15px;
        padding-bottom: 5px;
    }
    .title {
        font-size: 16pt;
        font-weight: bold;
        color: #003d9b;
    }
    .filters {
        font-size: 8pt;
        color: #5c5f60;
        margin-bottom: 10px;
    }
    .ledger-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 15px;
    }
    .ledger-table th {
        background-color: #f0f3ff;
        color: #003d9b;
        text-align: left;
        padding: 4px;
        font-size: 8pt;
        font-weight: bold;
        border-bottom: 1px solid #c3c6d6;
    }
    .ledger-table td {
        padding: 4px;
        border-bottom: 1px solid #dee2e2;
        font-size: 8pt;
    }
    .summary-box {
        width: 100%;
        border: 1px solid #dee0e2;
        background-color: #f9f9ff;
        padding: 10px;
        margin-bottom: 15px;
        font-size: 9pt;
    }
</style>
</head>
<body>
    <table class="header-table">
        <tr>
            <td>
                <div class="title">PharmaCore Financial Summary Report</div>
                <div class="filters">Generated on: {{ date_generated }} | Date Range: {{ start_date }} to {{ end_date }}</div>
            </td>
            <td style="text-align: right; font-size: 9pt; color: #5c5f60;">
                <strong>Outlet:</strong> All Stores
            </td>
        </tr>
    </table>

    <div class="summary-box">
        <strong>SUMMARY TOTALS</strong> (excluding {{ summary_totals.cancelled_count }} cancelled):&nbsp;&nbsp;
        Gross Sales: ₹{{ "%.2f" | format(summary_totals.gross_total) }} &nbsp;|&nbsp;
        Discounts: ₹{{ "%.2f" | format(summary_totals.discount_total) }} &nbsp;|&nbsp;
        GST: ₹{{ "%.2f" | format(summary_totals.gst_total) }} &nbsp;|&nbsp;
        Net Amount: ₹{{ "%.2f" | format(summary_totals.net_total) }} &nbsp;|&nbsp;
        Paid: ₹{{ "%.2f" | format(summary_totals.paid_total) }} &nbsp;|&nbsp;
        Refunded: ₹{{ "%.2f" | format(summary_totals.refund_total) }} &nbsp;|&nbsp;
        Due: ₹{{ "%.2f" | format(summary_totals.due_total) }}
    </div>

    <table class="ledger-table">
        <thead>
            <tr>
                <th style="width: 15%;">Date</th>
                <th style="width: 10%;">Invoice ID</th>
                <th style="width: 20%;">Patient Name</th>
                <th style="width: 12%;">Bill Type</th>
                <th style="width: 10%;">Payment</th>
                <th style="width: 8%; text-align: right;">Gross</th>
                <th style="width: 8%; text-align: right;">GST</th>
                <th style="width: 9%; text-align: right;">Net</th>
                <th style="width: 8%; text-align: center;">Status</th>
            </tr>
        </thead>
        <tbody>
            {% for inv in data %}
            <tr>
                <td>{{ inv.date_formatted }}</td>
                <td>{{ inv.id }}</td>
                <td>{{ inv.patient_name }}</td>
                <td>{{ inv.bill_type }}</td>
                <td>{{ inv.payment_method }}</td>
                <td style="text-align: right;">₹{{ "%.2f" | format(inv.gross_amount) }}</td>
                <td style="text-align: right;">₹{{ "%.2f" | format(inv.tax_breakdown.total_gst) }}</td>
                <td style="text-align: right;">₹{{ "%.2f" | format(inv.net_payable) }}</td>
                <td style="text-align: center;">{{ inv.status }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>"""


# Compiled once, not per request
_REPORT_TPL = Template(REPORT_TEMPLATE)
_INVOICE_TPL = Template(INVOICE_HTML)

# xhtml2pdf is synchronous and CPU-heavy: render in worker threads, two at a time, so a
# large report never freezes other requests
_pdf_slots = asyncio.Semaphore(2)
MAX_PDF_REPORT_ROWS = 5000


def _render_pdf_sync(template: Template, context: dict) -> bytes:
    buffer = io.BytesIO()
    if pisa.CreatePDF(template.render(**context), dest=buffer).err:
        raise RuntimeError("xhtml2pdf reported an error")
    return buffer.getvalue()


async def render_pdf(template: Template, context: dict) -> bytes:
    async with _pdf_slots:
        return await run_in_threadpool(_render_pdf_sync, template, context)


def _format_dt(value, tz: timezone) -> str:
    dt = utc(value)
    return dt.astimezone(tz).strftime("%b %d, %Y - %H:%M") if dt else ""


@router.get("/billing/invoices/export/pdf")
async def export_invoices_to_pdf(
    filters: dict = Depends(invoice_filters),
    tz_offset: int = Query(0, ge=-14 * 60, le=14 * 60),
):
    res = await service.list_invoices({**filters, "sort_by": "date", "sort_order": "desc"},
                                      page=1, limit=MAX_PDF_REPORT_ROWS)
    if res["pagination"]["total_records"] > MAX_PDF_REPORT_ROWS:
        raise HTTPException(status_code=400, detail=(
            f"The PDF report is limited to {MAX_PDF_REPORT_ROWS} invoices; this selection has "
            f"{res['pagination']['total_records']}. Narrow the filters or use the CSV export."))
    tz = timezone(timedelta(minutes=tz_offset))
    rows = [dict(inv, date_formatted=_format_dt(inv.get("date"), tz)) for inv in res["data"]]
    context = {
        "data": rows,
        "summary_totals": res["summary_totals"],
        "date_generated": datetime.now(tz).strftime("%b %d, %Y - %H:%M"),
        "start_date": filters.get("start_date") or "All Time",
        "end_date": filters.get("end_date") or "All Time",
    }
    try:
        pdf = await render_pdf(_REPORT_TPL, context)
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to render the PDF report")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=billing_report.pdf"},
    )


@router.get("/billing/invoices/{invoice_id}", response_model=schemas.InvoiceOut)
async def read_single_invoice(invoice_id: str):
    inv = await service.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/billing/invoices", status_code=status.HTTP_201_CREATED, response_model=schemas.InvoiceOut)
async def create_new_invoice(invoice: schemas.InvoiceCreate, user: dict = Depends(get_current_user)):
    return await service.create_invoice(invoice.model_dump(), actor=user["full_name"])


@router.post("/billing/invoices/{invoice_id}/cancel", response_model=schemas.InvoiceOut)
async def cancel_existing_invoice(invoice_id: str, user: dict = Depends(require_pharmacist)):
    inv = await service.cancel_invoice(invoice_id, user["full_name"])
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/billing/invoices/{invoice_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=schemas.InvoiceOut)
async def duplicate_existing_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    inv = await service.duplicate_invoice(invoice_id, user["full_name"])
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/billing/invoices/{invoice_id}/refund", response_model=schemas.InvoiceOut)
async def refund_existing_invoice(
    invoice_id: str,
    refund_amount: float = Query(..., gt=0),
    reason: str = Query(..., min_length=1, max_length=500),
    user: dict = Depends(require_pharmacist),
):
    inv = await service.process_refund(invoice_id, refund_amount, reason, user["full_name"])
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.delete("/billing/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_pharmacist)])
async def delete_existing_invoice(invoice_id: str):
    deleted = await service.delete_invoice(invoice_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/billing/invoices/{invoice_id}/pdf")
async def download_invoice_pdf_file(
    invoice_id: str,
    tz_offset: int = Query(0, ge=-14 * 60, le=14 * 60),
    inline: bool = Query(False, description="Display in the browser (for printing) instead of downloading"),
):
    inv = await service.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    context = dict(inv)
    context["date"] = _format_dt(inv.get("date"), timezone(timedelta(minutes=tz_offset)))
    try:
        pdf = await render_pdf(_INVOICE_TPL, context)
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to generate the invoice PDF")

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"{'inline' if inline else 'attachment'}; filename=invoice_{inv['id']}.pdf"},
    )
