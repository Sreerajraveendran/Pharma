"""Pure functions: tax, pricing, date parsing, metrics, CSV safety, password policy."""
from datetime import datetime, timezone

import pytest

from app.modules.auth.security import password_policy_error
from app.modules.billing import service as billing
from app.modules.pos.service import price_lines


def test_gst_added_on_top():
    taxes = billing.calculate_invoice_taxes(100.0, 10.0)
    assert taxes == {"cgst": 5.4, "sgst": 5.4, "igst": 0.0, "total_gst": 10.8, "inclusive": False}
    assert billing.net_payable_for(100.0, 10.0, taxes) == 100.8


def test_gst_included_in_mrp():
    taxes = billing.calculate_invoice_taxes(112.0, 0.0, inclusive=True)
    assert taxes["total_gst"] == 12.0
    assert taxes["cgst"] + taxes["sgst"] == taxes["total_gst"]
    assert billing.net_payable_for(112.0, 0.0, taxes) == 112.0


def test_gst_split_never_drifts_by_a_paisa():
    taxes = billing.calculate_invoice_taxes(10.01, 0.0)
    assert round(taxes["cgst"] + taxes["sgst"], 2) == taxes["total_gst"]


def test_price_lines_uses_mrp_and_extracts_gst():
    lines = [{"batch_id": "b1", "medicine_id": "m1", "name": "Crocin", "batch_number": "C1", "quantity": 2, "mrp": 15.0}]
    items, gross, discount = price_lines(lines, 10)
    assert (gross, discount) == (30.0, 3.0)
    assert items[0]["gst"] == round(27 - 27 / 1.12, 2)
    assert items[0]["credited_to_prescription"] == 0


def test_date_only_bounds_cover_whole_utc_day():
    # (instant, inclusive): an end date becomes the next midnight, exclusive
    assert billing._parse_date_bound("2026-10-05", False) == (datetime(2026, 10, 5, tzinfo=timezone.utc), True)
    assert billing._parse_date_bound("2026-10-05", True) == (datetime(2026, 10, 6, tzinfo=timezone.utc), False)


def test_timestamp_bounds_are_used_as_given():
    value, inclusive = billing._parse_date_bound("2026-10-04T18:30:00.000Z", True)
    assert inclusive and value == datetime(2026, 10, 4, 18, 30, tzinfo=timezone.utc)


def test_invalid_date_is_a_client_error():
    with pytest.raises(billing.InvoiceError):
        billing._parse_date_bound("not-a-date", False)


def test_compute_metrics_excludes_cancelled_and_nets_refunds():
    now = datetime.now(timezone.utc)
    base = {"date": now, "gross_amount": 100.0, "discount_applied": 0.0, "net_payable": 112.0,
            "tax_breakdown": {"total_gst": 12.0}, "balance_due": 0.0, "bill_type": "POS Sale"}
    invoices = [
        {**base, "status": "Paid", "payment_method": "Cash", "amount_paid": 112.0, "refunded_amount": 0.0},
        {**base, "status": "Partially Refunded", "payment_method": "UPI", "amount_paid": 112.0, "refunded_amount": 40.0},
        {**base, "status": "Cancelled", "payment_method": "Cash", "amount_paid": 0.0, "refunded_amount": 0.0},
    ]
    m = billing.compute_metrics(invoices)
    assert m["num_transactions"] == 2
    assert m["total_revenue"] == 184.0          # 112 + (112 - 40)
    assert m["total_refunds"] == 40.0
    assert m["net_revenue"] == 224.0 - 40.0
    assert m["cash_collection"] == 112.0 and m["upi_collection"] == 72.0
    assert m["avg_bill_value"] == 112.0


@pytest.mark.parametrize("value,expected", [
    ("=SUM(A1)", "'=SUM(A1)"), ("+91 98", "'+91 98"), ("-5", "'-5"), ("@x", "'@x"), ("Jane", "Jane"), (None, None),
])
def test_csv_cells_cannot_start_formulas(value, expected):
    assert billing._csv_safe(value) == expected


@pytest.mark.parametrize("password,email,name,ok", [
    ("short", "a@b.co", "", False),
    ("Granite-Harbor-Lantern-42", "admin@test.local", "", True),
    ("my-admin-passphrase-1", "admin@test.local", "", False),     # contains the email name
    ("Jane Smith rocks 2026!", "j@x.io", "Jane Smith", False),     # contains the full name
    ("aaaaaaaaaaaaaaaa", "x@y.io", "", False),                     # too repetitive
])
def test_password_policy(password, email, name, ok):
    assert (password_policy_error(password, email, name) is None) is ok
