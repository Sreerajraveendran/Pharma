"""Invoices, refunds/cancellations, KPIs and charts (SQL vs the Python reference) and exports."""
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest

from app.modules.billing import service as billing
from app.modules.billing import repository as invoices_repo

pytestmark = pytest.mark.usefixtures("demo_data")

MANUAL_INVOICE = {
    "patient_name": "Probe Patient", "patient_type": "Walk-in", "doctor_name": "Dr X", "bill_type": "POS Sale",
    "payment_method": "Cash", "gross_amount": 100.0, "discount_applied": 0.0, "store_name": "s",
    "billing_items": [{"name": "Probe Med", "quantity": 1, "batch_number": "B1", "unit_price": 100.0,
                       "discount": 0, "gst": 12, "total_price": 100.0}],
}


def q(**params) -> str:
    return "?" + urlencode({k: v for k, v in params.items() if v is not None})


async def ledger(api, **params):
    res = await api.get("/api/billing/invoices" + q(**params))
    assert res.status_code == 200, res.text
    return res.json()


async def create_invoice(api, **overrides) -> dict:
    res = await api.post("/api/billing/invoices", json={**MANUAL_INVOICE, **overrides})
    assert res.status_code == 201, res.text
    return res.json()


async def test_ledger_uses_invoice_numbers(admin):
    data = (await ledger(admin, limit=10))["data"]
    assert data and all(i["id"].startswith("INV-") for i in data)


async def test_cancel_refund_delete_persist(admin):
    a, b, c = (await ledger(admin, status="Paid", limit=3, sort_by="net_payable"))["data"]

    assert (await admin.post(f"/api/billing/invoices/{a['id']}/cancel")).status_code == 200
    assert (await admin.get(f"/api/billing/invoices/{a['id']}")).json()["status"] == "Cancelled"

    assert (await admin.post(f"/api/billing/invoices/{b['id']}/refund" + q(refund_amount=10, reason="partial"))).status_code == 200
    fresh = (await admin.get(f"/api/billing/invoices/{b['id']}")).json()
    assert fresh["status"] == "Partially Refunded" and fresh["refunded_amount"] == 10

    assert (await admin.delete(f"/api/billing/invoices/{c['id']}")).status_code == 204
    assert (await admin.get(f"/api/billing/invoices/{c['id']}")).status_code == 404


async def test_create_invoice_numbers_are_unique_after_kpi_loads(admin):
    ids = []
    for _ in range(3):
        await admin.get("/api/billing/invoices/kpis" + q(start_date=(datetime.now(timezone.utc) - timedelta(days=7)).isoformat()))
        ids.append((await create_invoice(admin))["id"])
    assert len(set(ids)) == 3
    assert (await admin.get(f"/api/billing/invoices/{ids[0]}")).json()["net_payable"] == 112.0, "manual invoices add GST on top"


async def test_date_filters(admin):
    today = datetime.now(timezone.utc).date()
    week = await ledger(admin, start_date=str(today - timedelta(days=6)), end_date=str(today))
    assert week["pagination"]["total_records"] > 0

    await create_invoice(admin, patient_name="Today Probe")
    same_day = await ledger(admin, start_date=str(today), end_date=str(today), search="Today Probe")
    assert same_day["pagination"]["total_records"] == 1, "end_date must include the whole day"

    ist = timezone(timedelta(hours=5, minutes=30))
    start = datetime.combine(today, datetime.min.time(), tzinfo=ist).astimezone(timezone.utc)
    res = await admin.get("/api/billing/invoices" + q(start_date=start.isoformat().replace("+00:00", "Z"),
                                                      end_date=(start + timedelta(days=1, milliseconds=-1)).isoformat().replace("+00:00", "Z")))
    assert res.status_code == 200

    assert (await admin.get("/api/billing/invoices" + q(start_date="not-a-date"))).status_code == 400
    one = (await ledger(admin, limit=1))["data"][0]
    assert str(one["date"]).endswith(("+00:00", "Z")), "dates must carry a UTC offset"


@pytest.mark.parametrize("term", ["(", "+91", "INV-1"])
async def test_search_is_literal_not_regex(admin, term):
    assert (await admin.get("/api/billing/invoices" + q(search=term))).status_code == 200


async def test_refund_and_cancel_rules(admin):
    inv = (await create_invoice(admin))["id"]
    url = f"/api/billing/invoices/{inv}"
    assert (await admin.post(url + "/refund" + q(refund_amount=99999, reason="x"))).status_code == 400
    assert (await admin.post(url + "/refund" + q(refund_amount=-50, reason="x"))).status_code == 422
    res = await admin.post(url + "/refund" + q(refund_amount=40, reason="part 1"))
    assert res.status_code == 200 and res.json()["status"] == "Partially Refunded"
    assert (await admin.post(url + "/cancel")).status_code == 400, "invoices with refunds can't be cancelled"
    res = await admin.post(url + "/refund" + q(refund_amount=72, reason="rest"))
    body = res.json()
    assert body["status"] == "Refunded" and body["refunded_amount"] == 112 and len(body["refunds"]) == 2
    assert (await admin.post(url + "/refund" + q(refund_amount=1, reason="again"))).status_code == 400

    other = (await create_invoice(admin))["id"]
    assert (await admin.post(f"/api/billing/invoices/{other}/cancel")).status_code == 200
    assert (await admin.post(f"/api/billing/invoices/{other}/cancel")).status_code == 400
    assert (await admin.post(f"/api/billing/invoices/{other}/refund" + q(refund_amount=1, reason="x"))).status_code == 400


async def test_kpis_match_the_ledger(admin):
    unfiltered = (await admin.get("/api/billing/invoices/kpis")).json()
    assert unfiltered["total_revenue"]["change"] is None, "no start date means no comparison"

    start = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    k = (await admin.get("/api/billing/invoices/kpis" + q(start_date=start))).json()
    totals = (await ledger(admin, start_date=start, limit=1))["summary_totals"]
    assert len(k["total_revenue"]["sparkline"]) == 10
    assert abs(sum(k["total_revenue"]["sparkline"]) - k["total_revenue"]["raw"]) < 0.05
    assert abs(k["total_revenue"]["raw"] - totals["net_collected"]) < 0.01
    assert abs(k["total_refunds"]["raw"] - totals["refund_total"]) < 0.01
    assert abs(k["net_revenue"]["raw"] - (totals["net_total"] - totals["refund_total"])) < 0.01


async def test_kpis_equal_reference_metrics(admin, db):
    """The KPIs are computed in SQL; they must equal the Python reference implementation."""
    start = datetime.now(timezone.utc) - timedelta(days=14)
    k = (await admin.get("/api/billing/invoices/kpis" + q(start_date=start.isoformat()))).json()
    invoices = await invoices_repo.find_all(invoices_repo.InvoiceFilter(start=start))
    reference = billing.compute_metrics(invoices)
    for key, value in reference.items():
        assert abs(k[key]["raw"] - value) < 0.01, key

    # Sparkline buckets also match the reference, slice by slice
    end = datetime.now(timezone.utc)
    width = (end - start) / billing.SPARKLINE_POINTS
    buckets = [[] for _ in range(billing.SPARKLINE_POINTS)]
    for inv in invoices:
        buckets[min(int((inv["date"] - start) / width), billing.SPARKLINE_POINTS - 1)].append(inv)
    expected = [billing.compute_metrics(b)["total_revenue"] for b in buckets]
    assert all(abs(a - b) < 0.01 for a, b in zip(k["total_revenue"]["sparkline"], expected))


async def test_charts_equal_reference_totals(admin):
    today = datetime.now(timezone.utc).date()
    params = dict(start_date=str(today - timedelta(days=13)), end_date=str(today))
    charts = (await admin.get("/api/billing/invoices/charts" + q(**params, tz_offset=330))).json()
    rows = (await ledger(admin, **params, limit=500))["data"]
    kept = [i for i in rows if i["status"] != "Cancelled"]
    collected = sum(i["amount_paid"] - i["refunded_amount"] for i in kept)
    assert abs(sum(r["revenue"] for r in charts["revenue_trend"]) - collected) < 0.05
    assert abs(sum(r["value"] for r in charts["payment_distribution"]) - collected) < 0.05
    assert len(charts["revenue_trend"]) == 15, "14 UTC days seen from IST (+05:30) touch 15 local days"
    assert len(charts["top_medicines"]) == 5
    values = [r["value"] for r in charts["top_medicines"]]
    assert values == sorted(values, reverse=True)


async def test_concurrent_refunds_cannot_exceed_the_payment(admin):
    inv = await create_invoice(admin)
    half_and_more = round(inv["amount_paid"] * 0.6, 2)
    results = await asyncio.gather(*[
        admin.post(f"/api/billing/invoices/{inv['id']}/refund" + q(refund_amount=half_and_more, reason="race"))
        for _ in range(4)])
    assert sorted(r.status_code for r in results) == [200, 400, 400, 400]
    final = (await admin.get(f"/api/billing/invoices/{inv['id']}")).json()
    assert final["refunded_amount"] == half_and_more and len(final["refunds"]) == 1


async def test_refunds_are_not_revenue(admin):
    for inv in (await ledger(admin, status="Refunded", limit=500))["data"]:
        assert inv["amount_paid"] - inv["refunded_amount"] == 0


async def test_charts_follow_filters(admin):
    today = datetime.now(timezone.utc).date()
    short = (await admin.get("/api/billing/invoices/charts" + q(start_date=str(today - timedelta(days=2)), end_date=str(today)))).json()
    assert len(short["revenue_trend"]) == 3
    long = (await admin.get("/api/billing/invoices/charts" + q(start_date=str(today - timedelta(days=200)), end_date=str(today)))).json()
    assert 7 <= len(long["revenue_trend"]) <= 8, "long ranges bucket by month"
    assert (await admin.get("/api/billing/invoices/charts" + q(tz_offset=330))).status_code == 200


async def test_duplicate_is_an_unpaid_copy(admin):
    source = (await create_invoice(admin))["id"]
    before = (await admin.get("/api/billing/invoices/kpis")).json()
    res = await admin.post(f"/api/billing/invoices/{source}/duplicate")
    dup = res.json()
    after = (await admin.get("/api/billing/invoices/kpis")).json()
    assert res.status_code == 201 and dup["status"] == "Pending" and dup["amount_paid"] == 0
    assert dup["duplicated_from"] == source
    assert before["total_revenue"]["raw"] == after["total_revenue"]["raw"]
    assert round(after["pending_payments"]["raw"] - before["pending_payments"]["raw"], 2) == dup["net_payable"]


async def test_filter_options_come_from_data(admin):
    opts = (await admin.get("/api/billing/invoices/filter-options")).json()
    assert opts["payment_methods"] == ["Card", "Cash", "UPI"]
    assert "Rahul Verma" in opts["cashiers"]


async def test_exports(admin):
    today = datetime.now(timezone.utc).date()
    csv = await admin.get("/api/billing/invoices/export/csv" + q(doctor="Dr. Alex Carter"))
    assert csv.status_code == 200 and csv.text.startswith("Invoice ID,")
    pdf = await admin.get("/api/billing/invoices/export/pdf" + q(start_date=str(today - timedelta(days=6)), end_date=str(today), tz_offset=330))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


async def test_invoice_pdf_download_and_inline(admin):
    inv = (await ledger(admin, limit=1))["data"][0]["id"]
    download = await admin.get(f"/api/billing/invoices/{inv}/pdf?tz_offset=330")
    inline = await admin.get(f"/api/billing/invoices/{inv}/pdf?inline=true")
    assert download.content[:4] == inline.content[:4] == b"%PDF"
    assert download.headers["content-disposition"].startswith("attachment")
    assert inline.headers["content-disposition"].startswith("inline")
