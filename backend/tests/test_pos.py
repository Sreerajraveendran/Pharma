"""POS checkout, stock safety, prescriptions, dashboard, and input validation."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.usefixtures("demo_data")


async def batch(api, number: str) -> dict:
    return next(b for b in (await api.get("/api/batches")).json() if b["batch_number"] == number)


async def patient(api, name: str) -> dict:
    return next(p for p in (await api.get("/api/patients")).json() if p["name"] == name)


async def checkout(api, **body):
    return await api.post("/api/pos/checkout", json=body)


async def test_checkout_creates_a_priced_invoice(admin):
    crocin = await batch(admin, "CRO322")
    res = await checkout(admin, items=[{"batch_id": crocin["id"], "quantity": 2, "unit_mrp": 0.01}],
                         payment_method="UPI", discount_percent=10)
    assert res.status_code == 200, res.text
    sale = res.json()
    assert sale["total_amount"] == 2 * crocin["mrp"], "price must come from the batch, not the client"
    assert sale["net_amount"] == round(2 * crocin["mrp"] * 0.9, 2) and sale["gst_included"] > 0

    inv = (await admin.get(f"/api/billing/invoices/{sale['invoice_id']}")).json()
    assert inv["payment_method"] == "UPI" and inv["cashier_name"] == "System Administrator" and inv["stock_deducted"]
    assert (await batch(admin, "CRO322"))["quantity_on_hand"] == crocin["quantity_on_hand"] - 2


@pytest.mark.parametrize("quantity,extra", [
    (-50, {}),
    (1, {"discount_percent": 150}),
    (1, {"payment_method": "Bitcoin"}),
])
async def test_checkout_rejects_bad_input(admin, quantity, extra):
    crocin = await batch(admin, "CRO322")
    res = await checkout(admin, items=[{"batch_id": crocin["id"], "quantity": quantity}], **extra)
    assert res.status_code == 422


async def test_split_lines_are_checked_together(admin):
    met = await batch(admin, "MET404")
    q = met["quantity_on_hand"]
    res = await checkout(admin, items=[{"batch_id": met["id"], "quantity": q - 1}, {"batch_id": met["id"], "quantity": 2}])
    assert res.status_code == 400 and "Insufficient" in res.json()["detail"]


async def test_concurrent_sales_never_oversell(admin, db):
    met = await batch(admin, "MET404")
    await db.execute("UPDATE batches SET quantity_on_hand = 10 WHERE id = :id", id=met["id"])
    results = await asyncio.gather(*[checkout(admin, items=[{"batch_id": met["id"], "quantity": 4}]) for _ in range(6)])
    assert sorted(r.status_code for r in results).count(200) == 2
    assert (await batch(admin, "MET404"))["quantity_on_hand"] == 2


async def test_expired_batch_cannot_be_sold(admin, db):
    aug = await batch(admin, "AUG920")
    await db.execute("INSERT INTO batches (medicine_id, batch_number, expiry_date, quantity_on_hand, location_code, "
                     "purchase_price, mrp) VALUES (:med, 'EXPIRED1', :expiry, 50, 'X', 1, 10)",
                     med=aug["medicine_id"], expiry=datetime.now(timezone.utc) - timedelta(days=1))
    expired = await batch(admin, "EXPIRED1")
    res = await checkout(admin, items=[{"batch_id": expired["id"], "quantity": 1}])
    assert res.status_code == 400 and "expired" in res.json()["detail"]


async def test_prescription_rules_and_cancel_reversal(admin):
    jane, john = await patient(admin, "Jane Smith"), await patient(admin, "John Doe")
    rx = next(r for r in (await admin.get(f"/api/patients/{jane['id']}/prescriptions")).json() if r["status"] == "Active")
    crocin = await batch(admin, "CRO322")

    other = await checkout(admin, patient_id=john["id"], prescription_id=rx["id"], items=[{"batch_id": crocin["id"], "quantity": 1}])
    assert other.status_code == 400, "another patient's prescription"
    over = await checkout(admin, patient_id=jane["id"], prescription_id=rx["id"], items=[{"batch_id": crocin["id"], "quantity": 16}])
    assert over.status_code == 400 and "remaining" in over.json()["detail"]

    res = await checkout(admin, patient_id=jane["id"], prescription_id=rx["id"], items=[{"batch_id": crocin["id"], "quantity": 5}])
    assert res.status_code == 200
    sale = res.json()
    assert (await admin.get(f"/api/prescriptions/{rx['id']}")).json()["medicines"][0]["dispensed_quantity"] == 5
    inv = (await admin.get(f"/api/billing/invoices/{sale['invoice_id']}")).json()
    assert inv["bill_type"] == "Prescription Sale" and inv["doctor_name"] == "Dr. Alex Carter"

    assert (await admin.post(f"/api/billing/invoices/{sale['invoice_id']}/cancel")).status_code == 200
    assert (await batch(admin, "CRO322"))["quantity_on_hand"] == crocin["quantity_on_hand"], "cancel returns stock"
    assert (await admin.get(f"/api/prescriptions/{rx['id']}")).json()["medicines"][0]["dispensed_quantity"] == 0


async def test_dashboard_matches_financial_kpis(admin):
    dash = (await admin.get("/api/dashboard/metrics?tz_offset=330")).json()
    start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    k = (await admin.get(f"/api/billing/invoices/kpis?start_date={start}")).json()
    assert abs(dash["total_revenue"] - k["total_revenue"]["raw"]) < 1.0
    assert dash["low_stock_alerts"] > 0 and dash["critical_expiry_alerts"] > 0
    assert len(dash["sales_chart"]) == 7


async def test_medicine_stock_and_expiry_status(admin):
    meds = {m["name"]: m for m in (await admin.get("/api/medicines")).json()}
    assert meds["Augmentin 625 Duo"]["expiry_status"] == "CRITICAL"
    assert meds["Metformin 500mg"]["stock_level_status"] in ("LOW", "OUT_OF_STOCK")


# Validation

async def test_batch_validation(admin):
    med = (await admin.get("/api/medicines")).json()[0]
    future = (datetime.now(timezone.utc) + timedelta(days=300)).isoformat()
    base = {"medicine_id": med["id"], "batch_number": "P1", "expiry_date": future, "quantity_on_hand": 5,
            "location_code": "A", "purchase_price": 1, "mrp": 2}
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert (await admin.post("/api/batches", json={**base, "expiry_date": past})).status_code == 422
    assert (await admin.post("/api/batches", json={**base, "quantity_on_hand": -100})).status_code == 422
    res = await admin.post("/api/batches", json={**base, "batch_number": "P3"})
    assert res.status_code == 201 and res.json()["batch_number"] == "P3"


async def test_prescription_validation(admin):
    jane = await patient(admin, "Jane Smith")
    med = (await admin.get("/api/medicines")).json()[0]
    line = {"medicine_id": med["id"], "dosage_instruction": "x", "duration_days": 5, "quantity_prescribed": 5}
    assert (await admin.post("/api/prescriptions", json={"patient_id": jane["id"], "prescribed_by": "Dr Y",
                                                         "medicines": [{**line, "medicine_id": "bogus"}]})).status_code == 400
    assert (await admin.post("/api/prescriptions", json={"patient_id": jane["id"], "prescribed_by": "Dr Y",
                                                         "medicines": [{**line, "quantity_prescribed": -5}]})).status_code == 422
    res = await admin.post("/api/prescriptions", json={"patient_id": jane["id"], "prescribed_by": "Dr Y", "status": "Fully Dispensed",
                                                       "medicines": [{**line, "dispensed_quantity": 99}]})
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "Active" and body["medicines"][0]["dispensed_quantity"] == 0


async def test_template_module_is_gone(admin):
    for method, url in [("GET", "/api/templates"), ("GET", "/api/templates/tpl_002"), ("POST", "/api/documents/generate")]:
        assert (await admin.request(method, url)).status_code in (404, 405)
    paths = (await admin.get("/openapi.json")).json()["paths"]
    assert not any("template" in p or "documents" in p for p in paths)
