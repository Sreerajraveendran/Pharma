import logging
from typing import Dict, List, Optional, Tuple

from app.core import config
from app.modules.billing import service as billing_service
from app.core.common import gst_included_in, now_utc, parse_id, utc
from app.db.engine import transaction
from app.modules.pos import repository as audit
from app.modules.medicines import repository as catalog
from app.modules.patients import repository as people

logger = logging.getLogger("app.modules.pos.service")


class CheckoutError(Exception):
    """A checkout that can't be completed (maps to HTTP 400)."""


async def _load_lines(items: List[dict]) -> List[dict]:
    """Validates the cart against the database. Prices come from the batch, never the client.
    The batches are locked until the checkout transaction ends. Two queries for any cart size."""
    qty_by_batch: Dict[str, int] = {}
    for item in items:
        # Several cart lines for one batch must be checked against its stock together
        qty_by_batch[item["batch_id"]] = qty_by_batch.get(item["batch_id"], 0) + item["quantity"]

    for batch_id in qty_by_batch:
        if parse_id(batch_id) is None:
            raise CheckoutError(f"Invalid batch ID: {batch_id}")
    batches = await catalog.batches_by_ids(qty_by_batch, lock=True)
    names = await catalog.medicines_by_ids({b["medicine_id"] for b in batches.values()}, fields=["name"])

    now = now_utc()
    lines = []
    for batch_id, qty in qty_by_batch.items():
        batch = batches.get(batch_id)
        if not batch:
            raise CheckoutError(f"Batch {batch_id} not found")
        med = names.get(batch["medicine_id"])
        name = med["name"] if med else "Unknown medicine"

        expiry = utc(batch.get("expiry_date"))
        if expiry and expiry <= now:
            raise CheckoutError(f"{name} batch {batch['batch_number']} expired on {expiry:%d %b %Y} and can't be sold.")
        if batch.get("quantity_on_hand", 0) < qty:
            raise CheckoutError(f"Insufficient stock for {name}. Requested: {qty}, "
                                f"Available: {batch.get('quantity_on_hand', 0)}")
        mrp = float(batch.get("mrp") or 0.0)
        if mrp <= 0:
            raise CheckoutError(f"{name} batch {batch['batch_number']} has no valid MRP.")
        lines.append({"batch_id": batch_id, "medicine_id": str(batch["medicine_id"]), "name": name,
                      "batch_number": batch["batch_number"], "quantity": qty, "mrp": mrp})
    return lines


async def _load_prescription(prescription_id: Optional[str], patient: Optional[dict]) -> Optional[dict]:
    if not prescription_id:
        return None
    if parse_id(prescription_id) is None:
        raise CheckoutError("Invalid prescription ID")
    rx = await people.get_prescription(prescription_id, lock=True)
    if not rx:
        raise CheckoutError("Prescription not found")
    if patient and rx.get("patient_id") != patient["id"]:
        raise CheckoutError("The selected prescription belongs to a different patient")
    if rx.get("status") != "Active":
        raise CheckoutError(f"The prescription is {str(rx.get('status')).lower()} and can't be dispensed against")
    return rx


def price_lines(lines: List[dict], discount_percent: float) -> Tuple[List[dict], float, float]:
    """Prices cart lines into invoice items. MRP includes GST, so the tax on each line
    (after its discount) is extracted rather than added. Returns (items, gross, discount)."""
    billing_items = []
    for line in lines:
        total = round(line["quantity"] * line["mrp"], 2)
        disc = round(total * discount_percent / 100.0, 2)
        billing_items.append({
            "name": line["name"],
            "medicine_id": line["medicine_id"],
            "batch_id": line["batch_id"],
            "batch_number": line["batch_number"],
            "quantity": line["quantity"],
            "unit_price": line["mrp"],
            "discount": disc,
            "gst": gst_included_in(total - disc, billing_service.GST_RATE),
            "total_price": total,
            "credited_to_prescription": line.get("credit", 0),
        })
    gross = round(sum(i["total_price"] for i in billing_items), 2)
    discount = round(sum(i["discount"] for i in billing_items), 2)
    return billing_items, gross, discount


async def execute_checkout(checkout_data: dict, user: dict) -> dict:
    """Sells the cart in one transaction: validates it against locked batch (and prescription)
    rows, deducts stock, records a paid invoice, writes the stock audit log and credits the
    prescription. Either all of it commits or none of it does."""
    async with transaction():
        invoice, billing_items = await _checkout(checkout_data, user)

    return {
        "success": True,
        "transaction_id": invoice["id"],
        "invoice_id": invoice["id"],
        "total_amount": invoice["gross_amount"],
        "discount_applied": invoice["discount_applied"],
        "net_amount": invoice["net_payable"],
        "gst_included": invoice["tax_breakdown"]["total_gst"],
        "items": [{"name": i["name"], "batch_number": i["batch_number"], "quantity": i["quantity"],
                   "unit_price": i["unit_price"], "discount": i["discount"], "total_price": i["total_price"]}
                  for i in billing_items],
        "message": f"Dispensed successfully. Invoice {invoice['id']}",
    }


async def _checkout(checkout_data: dict, user: dict) -> Tuple[dict, List[dict]]:
    lines = await _load_lines(checkout_data["items"])

    patient = None
    if checkout_data.get("patient_id"):
        patient = await people.get_patient(checkout_data["patient_id"])
        if not patient:
            raise CheckoutError("Patient not found")
    rx = await _load_prescription(checkout_data.get("prescription_id"), patient)
    if rx and not patient:
        patient = await people.get_patient(rx["patient_id"])

    # Credit prescribed medicines against the prescription, refusing to over-dispense
    if rx:
        remaining = {m["medicine_id"]: m["quantity_prescribed"] - m.get("dispensed_quantity", 0)
                     for m in rx.get("medicines", [])}
        for line in lines:
            if line["medicine_id"] in remaining:
                left = remaining[line["medicine_id"]]
                if line["quantity"] > left:
                    raise CheckoutError(f"{line['name']}: only {max(left, 0)} remaining on the prescription, "
                                        f"{line['quantity']} requested")
                line["credit"] = line["quantity"]
                remaining[line["medicine_id"]] -= line["quantity"]

    billing_items, gross, discount = price_lines(lines, checkout_data.get("discount_percent", 0.0))
    cashier = user.get("full_name", "Unknown")

    for line in lines:
        # The batches are locked and were checked above; this guard is the last line of defence
        if not await catalog.deduct_stock(line["batch_id"], line["quantity"]):
            raise CheckoutError(f"Insufficient stock for {line['name']} (batch {line['batch_number']}). "
                                "Another sale may have just used it; refresh and try again.")

    invoice = await billing_service.insert_invoice({
        "patient_id": patient["id"] if patient else None,
        "patient_name": patient["name"] if patient else "Walk-in Customer",
        "patient_phone": patient.get("phone") if patient else None,
        "patient_type": "Registered" if patient else "Walk-in",
        "doctor_name": rx.get("prescribed_by", "") if rx else "",
        "bill_type": "Prescription Sale" if rx else "POS Sale",
        "payment_method": checkout_data.get("payment_method", "Cash"),
        "gross_amount": gross,
        "discount_applied": discount,
        "billing_items": billing_items,
        "cashier_name": cashier,
        "store_name": config.STORE_NAME,
        "stock_deducted": True,
        "prescription_id": rx["id"] if rx else None,
    }, inclusive_tax=True, paid=True, actor=cashier)

    await audit.insert_logs([{
        "timestamp": now_utc(),
        "batch_id": line["batch_id"],
        "action_type": "Sale",
        "quantity_changed": -line["quantity"],
        "patient_id": patient["id"] if patient else None,
        "notes": f"POS Checkout {invoice['id']}",
    } for line in lines])

    if rx:
        for line in lines:
            if line.get("credit"):
                await people.adjust_dispensed(rx["id"], line["medicine_id"], line["credit"])
        await people.refresh_prescription_status(rx["id"])

    return invoice, billing_items


async def get_recent_audit_logs(limit: int = 50) -> List[dict]:
    """Latest stock movements with batch number and medicine name. Three queries in total."""
    logs = await audit.recent_logs(limit)
    batches = await catalog.batches_by_ids({log["batch_id"] for log in logs})
    names = await catalog.medicines_by_ids({b["medicine_id"] for b in batches.values()}, fields=["name"])
    for log in logs:
        batch = batches.get(log["batch_id"])
        med = names.get(batch["medicine_id"]) if batch else None
        log["batch_number"] = batch["batch_number"] if batch else "Unknown"
        log["medicine_name"] = med["name"] if med else "Unknown Medicine"
        log["timestamp"] = utc(log.get("timestamp"))
    return logs
