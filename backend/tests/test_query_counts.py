"""Guards against N+1 queries: each endpoint issues a bounded number of database commands,
independent of how many rows it returns. Counts exclude the per-request auth lookups."""
import pytest

from conftest import count_statements

pytestmark = pytest.mark.usefixtures("demo_data")

# endpoint -> max commands beyond the authentication baseline
BUDGETS = {
    "/api/medicines": 3,
    "/api/batches": 2,
    "/api/categories": 1,
    "/api/patients": 1,
    "/api/prescriptions": 4,
    "/api/pos/audit-logs": 3,
    "/api/dashboard/metrics": 7,
    # Reports aggregate in SQL: a fixed number of statements for any number of invoices
    "/api/billing/invoices": 3,
    "/api/billing/invoices/kpis?start_date=2026-01-01": 3,
    "/api/billing/invoices/charts": 6,
    "/api/billing/invoices/INV-100001": 4,
}


async def auth_baseline(admin) -> int:
    res, n = await count_statements(admin.get("/api/auth/me"))
    assert res.status_code == 200
    return n


@pytest.mark.parametrize("url,budget", BUDGETS.items())
async def test_query_budget(admin, url, budget):
    baseline = await auth_baseline(admin)
    res, n = await count_statements(admin.get(url))
    assert res.status_code == 200, res.text
    assert n - baseline <= budget, f"{url} issued {n - baseline} queries (budget {budget})"


async def test_patient_prescriptions_query_by_patient(admin):
    patient = (await admin.get("/api/patients")).json()[0]
    baseline = await auth_baseline(admin)
    res, n = await count_statements(admin.get(f"/api/patients/{patient['id']}/prescriptions"))
    assert res.status_code == 200
    assert n - baseline <= 5
