"""PostgreSQL guarantees: constraints, transactional checkout, and the migrations themselves."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.pos import service as pos
from app.modules.pos import repository as audit

from conftest import SERVER_URL, TEST_DB_PREFIX, _admin_execute, alembic

pytestmark = pytest.mark.usefixtures("demo_data")


async def test_stock_cannot_go_negative(db):
    with pytest.raises(IntegrityError):
        await db.execute("UPDATE batches SET quantity_on_hand = -1 WHERE batch_number = 'CRO322'")


async def test_prescriptions_cannot_be_over_dispensed(db):
    with pytest.raises(IntegrityError):
        await db.execute("UPDATE prescription_lines SET dispensed_quantity = quantity_prescribed + 1")


async def test_refunds_cannot_exceed_the_payment(db):
    with pytest.raises(IntegrityError):
        await db.execute("UPDATE invoices SET refunded_amount = amount_paid + 1 WHERE status = 'Paid'")


async def test_failed_checkout_changes_nothing(db, monkeypatch):
    """A failure after stock was deducted and the invoice written rolls all of it back."""
    batch = await db.one("SELECT id::text, quantity_on_hand FROM batches WHERE batch_number = 'CRO322'")
    invoices = await db.scalar("SELECT count(*) FROM invoices")
    logs = await db.scalar("SELECT count(*) FROM audit_logs")

    async def broken(_):
        raise RuntimeError("audit log write failed")

    monkeypatch.setattr(audit, "insert_logs", broken)
    with pytest.raises(RuntimeError):
        await pos.execute_checkout({"items": [{"batch_id": batch["id"], "quantity": 2}]}, {"full_name": "Tester"})

    assert await db.scalar("SELECT quantity_on_hand FROM batches WHERE id = :id", id=batch["id"]) == batch["quantity_on_hand"]
    assert await db.scalar("SELECT count(*) FROM invoices") == invoices
    assert await db.scalar("SELECT count(*) FROM audit_logs") == logs


async def test_migrations_downgrade_and_upgrade_cleanly():
    name = f"{TEST_DB_PREFIX}mig_{uuid.uuid4().hex[:8]}"
    url = SERVER_URL.set(database=name)
    await _admin_execute(f'CREATE DATABASE "{name}"')
    try:
        for step in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
            result = alembic(*step, url=url)
            assert result.returncode == 0, result.stderr
        check = alembic("check", url=url)
        assert check.returncode == 0, "app/db/tables.py and the migrations disagree:\n" + check.stdout + check.stderr
    finally:
        await _admin_execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
