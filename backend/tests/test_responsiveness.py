"""Heavy work (PDF rendering, password hashing) must not block other requests."""
import asyncio
import time

import pytest

from app.modules.billing import router as billing_views

pytestmark = pytest.mark.usefixtures("demo_data")


async def test_pdf_report_row_cap(admin, monkeypatch):
    monkeypatch.setattr(billing_views, "MAX_PDF_REPORT_ROWS", 10)
    res = await admin.get("/api/billing/invoices/export/pdf")
    assert res.status_code == 400 and "CSV" in res.json()["detail"]


async def test_other_requests_answer_while_a_pdf_renders(admin, make_client):
    anon = make_client()
    report = asyncio.create_task(admin.get("/api/billing/invoices/export/pdf"))
    await asyncio.sleep(0.05)  # let the render start

    started = time.perf_counter()
    res = await anon.get("/api/auth/config")
    elapsed = time.perf_counter() - started

    assert res.status_code == 200
    assert not report.done(), "the report should still be rendering for this test to mean anything"
    assert elapsed < 0.5, f"a cheap request took {elapsed:.2f}s while a PDF rendered"
    assert (await report).status_code == 200


async def test_logins_do_not_serialize_the_server(make_client):
    anon = make_client()
    logins = [asyncio.create_task(make_client().login("nobody@test.local", "wrong-password-123")) for _ in range(4)]
    await asyncio.sleep(0.01)
    started = time.perf_counter()
    assert (await anon.get("/api/auth/config")).status_code == 200
    assert time.perf_counter() - started < 0.5
    assert all(r.status_code == 401 for r in await asyncio.gather(*logins))
