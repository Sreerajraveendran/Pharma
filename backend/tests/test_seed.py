"""Demo data: internal consistency, reproducibility, reset safety and atomicity."""
from datetime import datetime, timezone

import pytest

from app.core import config
from app.db import seed
from app.modules.billing import repository as invoices_repo

from conftest import RESET_PHRASE

pytestmark = pytest.mark.usefixtures("demo_data")

EXPECTED_STOCK = {number: on_hand for _, number, _, on_hand, _, _ in seed.BATCHES}


async def all_invoices(db):
    """Every invoice in the API shape (with items, refunds and audit trail), by number."""
    numbers = await db.all("SELECT number FROM invoices ORDER BY number")
    return [await invoices_repo.get(invoices_repo.invoice_code(r["number"])) for r in numbers]


async def fingerprint(db) -> str:
    """The seeded history. Today's sales are left out: how many exist depends on the clock."""
    today = datetime.now(timezone.utc).date()
    invoices = [i for i in await all_invoices(db) if i["date"].date() < today]
    parts = ["".join(f"{x['name']}{x['quantity']}" for x in i["billing_items"]) + i["payment_method"] + i["status"]
             + f"{i['net_payable']:.2f}" for i in invoices]
    return f"{len(invoices)}|{'|'.join(parts)}"


async def test_invoice_arithmetic(db):
    invoices = await all_invoices(db)
    assert len(invoices) >= 200
    for i in invoices:
        assert abs(sum(x["total_price"] for x in i["billing_items"]) - i["gross_amount"]) < 0.01
        assert abs(i["gross_amount"] - i["discount_applied"] - i["net_payable"]) < 0.01, "MRP includes GST"
        assert abs(sum(x["gst"] for x in i["billing_items"]) - i["tax_breakdown"]["total_gst"]) <= 0.05


async def test_only_supported_types_and_methods(db):
    invoices = await all_invoices(db)
    assert {i["bill_type"] for i in invoices} <= {"POS Sale", "Prescription Sale"}
    assert {i["payment_method"] for i in invoices} <= {"Cash", "Card", "UPI"}
    assert {i["status"] for i in invoices} <= {"Paid", "Refunded", "Partially Refunded", "Cancelled"}
    assert all(not (i.get("insurance_details") or {}).get("provider") for i in invoices)
    assert all(x.get("batch_id") and x.get("medicine_id") for i in invoices for x in i["billing_items"])


async def test_prescription_sales_link_to_prescriptions(db):
    meds = {r["id"]: r for r in await db.all("SELECT id::text, prescription_required FROM medicines")}
    for inv in await all_invoices(db):
        if inv["bill_type"] == "Prescription Sale":
            assert inv["patient_type"] == "Registered"
            rx = await db.one("SELECT patient_id::text, prescribed_by FROM prescriptions WHERE id = :id",
                              id=inv["prescription_id"])
            assert rx["patient_id"] == inv["patient_id"] and rx["prescribed_by"] == inv["doctor_name"]
            lines = await db.all("SELECT medicine_id::text, dispensed_quantity FROM prescription_lines "
                                 "WHERE prescription_id = :id", id=inv["prescription_id"])
            for m in lines:
                credited = sum(x["credited_to_prescription"] for x in inv["billing_items"] if x["medicine_id"] == m["medicine_id"])
                assert credited == m["dispensed_quantity"]
        elif inv["patient_type"] == "Walk-in":
            assert all(not meds[x["medicine_id"]]["prescription_required"] for x in inv["billing_items"])


async def test_sales_stock_and_audit_logs_agree(db):
    invoices = await all_invoices(db)
    sold, logged = {}, {}
    for inv in invoices:
        for x in inv["billing_items"]:
            sold[x["batch_id"]] = sold.get(x["batch_id"], 0) + x["quantity"]
    for log in await db.all("SELECT batch_id::text, quantity_changed FROM audit_logs WHERE action_type = 'Sale'"):
        logged[log["batch_id"]] = logged.get(log["batch_id"], 0) - log["quantity_changed"]
    assert sold == logged

    returned = await db.scalar("SELECT coalesce(sum(quantity_changed), 0) FROM audit_logs WHERE action_type = 'Return'")
    cancelled = sum(x["quantity"] for i in invoices if i["status"] == "Cancelled" for x in i["billing_items"])
    assert returned == cancelled

    batches = await db.all("SELECT id::text, batch_number, quantity_on_hand, expiry_date FROM batches")
    assert {b["batch_number"]: b["quantity_on_hand"] for b in batches} == EXPECTED_STOCK
    expiry = {b["id"]: b["expiry_date"] for b in batches}
    assert all(expiry[x["batch_id"]] > i["date"] for i in invoices for x in i["billing_items"])


async def test_stock_movements_reconcile(db):
    """Per batch: received - sold + returned = on hand today."""
    moves = await db.all("SELECT batch_id::text, sum(quantity_changed) AS net FROM audit_logs GROUP BY batch_id")
    net = {m["batch_id"]: m["net"] for m in moves}
    for b in await db.all("SELECT id::text, quantity_on_hand FROM batches"):
        assert net.get(b["id"], 0) == b["quantity_on_hand"]


async def test_no_patient_is_sold_an_allergen(db):
    allergies = {p["id"]: p["allergies"] for p in await db.all("SELECT id::text, allergies FROM patients")}
    for i in await all_invoices(db):
        if i["patient_id"]:
            blocked = set().union(*(seed.ALLERGY_CONFLICTS.get(a, set()) for a in allergies[i["patient_id"]]))
            assert not blocked & {x["name"] for x in i["billing_items"]}, i["id"]


async def test_refunds_and_dates(db):
    now = datetime.now(timezone.utc)
    invoices = sorted(await all_invoices(db), key=lambda i: i["date"])
    assert all(i["date"] <= now for i in invoices)
    assert (now - invoices[0]["date"]).days >= 28
    numbers = [int(i["id"][4:]) for i in invoices]
    assert numbers == sorted(numbers), "invoice numbers follow dates"
    assert numbers[0] == 100001, "a reset restarts invoice numbering"
    for i in invoices:
        if i.get("refunded_amount", 0) > 0:
            expected = "Refunded" if i["refunded_amount"] >= i["amount_paid"] - 0.005 else "Partially Refunded"
            assert i["status"] == expected and len(i["refunds"]) == 1


async def test_people_and_open_prescriptions(db):
    patients = await db.all("SELECT id::text, name, phone FROM patients")
    assert all(p["phone"].startswith("+91 ") for p in patients)
    for name in ("John Doe", "Jane Smith"):
        p = next(p for p in patients if p["name"] == name)
        assert await db.scalar("SELECT count(*) FROM prescriptions WHERE patient_id = :id AND status = 'Active'",
                               id=p["id"]) == 1
    assert await db.scalar("SELECT count(DISTINCT store_name) FROM invoices") == 1


async def test_reset_requires_the_phrase_and_reproduces_data(admin, db):
    before = await fingerprint(db)
    assert (await admin.post("/api/settings/seed", json={"confirm": "yes"})).status_code == 400
    assert (await admin.post("/api/settings/seed")).status_code == 422
    assert await fingerprint(db) == before

    await admin.post("/api/patients", json={"name": "Real Person", "phone": "+91 90000 00000", "email": "r@example.com",
                                            "date_of_birth": "1990-01-01", "allergies": []})
    users_before = await db.scalar("SELECT count(*) FROM users")
    res = await admin.post("/api/settings/seed", json={"confirm": RESET_PHRASE})
    assert res.status_code == 200
    assert await fingerprint(db) == before, "the fixed random seed must reproduce identical data"
    assert await db.scalar("SELECT count(*) FROM patients WHERE name = 'Real Person'") == 0
    assert await db.scalar("SELECT count(*) FROM users") == users_before
    assert await db.scalar("SELECT count(*) FROM auth_events WHERE type IN "
                           "('demo_reset_started', 'demo_reset_completed')") >= 2
    assert (await admin.get("/api/auth/me")).status_code == 200, "the admin session survives a reset"


async def test_reset_disabled_in_production(admin, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_DEMO_RESET", False)
    assert (await admin.get("/api/settings/status")).json()["demo_reset_enabled"] is False
    assert (await admin.post("/api/settings/seed", json={"confirm": RESET_PHRASE})).status_code == 403


async def test_status_hides_credentials(admin):
    url = (await admin.get("/api/settings/status")).json()["database_url"]
    assert url.startswith("postgresql://") and "@" not in url and "***" not in url


async def test_seed_never_touches_existing_data(db):
    await db.execute("DELETE FROM app_meta WHERE key = :key", key=seed.MARKER_ID)  # no marker, but data present
    assert await seed.seed_database() is False


async def test_failed_reset_changes_nothing(db, monkeypatch):
    before = await fingerprint(db)
    real = seed._seed_demo_data

    async def crash():
        await real()  # wipes and reseeds inside the transaction...
        raise RuntimeError("simulated crash")  # ...then fails before committing

    monkeypatch.setattr(seed, "_seed_demo_data", crash)
    with pytest.raises(RuntimeError):
        await seed.seed_database(force_reset=True)
    assert await fingerprint(db) == before
    assert await db.scalar("SELECT count(*) FROM invoices") >= 200
