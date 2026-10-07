"""PostgreSQL schema (SQLAlchemy Core). The single source of truth for Alembic migrations:
change a table here, then `alembic revision --autogenerate -m "..."` and review the result.

Conventions: UUID primary keys (exposed to the API as strings), money as NUMERIC(12,2),
times as TIMESTAMPTZ, and CHECK constraints for rules the database can enforce itself.
"""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer,
    MetaData, Numeric, Sequence, String, Table, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

# Deterministic constraint names, so migrations can refer to them
metadata = MetaData(naming_convention={
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})

MONEY = Numeric(12, 2)
NOW = text("now()")


def pk():
    return Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def ts(name: str, nullable: bool = False, default: bool = False):
    return Column(name, DateTime(timezone=True), nullable=nullable, server_default=NOW if default else None)


# Catalogue

categories = Table(
    "categories", metadata, pk(),
    Column("name", Text, nullable=False),
    Column("color_code", Text, nullable=False),
)

medicines = Table(
    "medicines", metadata, pk(),
    Column("name", Text, nullable=False),
    Column("generic_name", Text, nullable=False),
    Column("form", Text, nullable=False),
    Column("dosage", Text, nullable=False),
    Column("category_id", UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False),
    Column("manufacturer", Text, nullable=False),
    Column("prescription_required", Boolean, nullable=False, server_default=text("false")),
    Column("storage_requirement", Text, nullable=False, server_default=""),
    Column("side_effects", Text, nullable=False, server_default=""),
    Column("min_stock_level", Integer, nullable=False, server_default="0"),
    Column("base_uom", Text, nullable=False, server_default="Strip"),
    CheckConstraint("min_stock_level >= 0", name="min_stock_non_negative"),
)

batches = Table(
    "batches", metadata, pk(),
    Column("medicine_id", UUID(as_uuid=True), ForeignKey("medicines.id"), nullable=False),
    Column("batch_number", Text, nullable=False),
    ts("expiry_date"),
    Column("quantity_on_hand", Integer, nullable=False),
    Column("supplier_id", Text),
    Column("location_code", Text, nullable=False),
    Column("purchase_price", MONEY, nullable=False),
    Column("mrp", MONEY, nullable=False),
    # Stock can never go negative, whatever the code does
    CheckConstraint("quantity_on_hand >= 0", name="stock_non_negative"),
    CheckConstraint("mrp > 0", name="mrp_positive"),
    CheckConstraint("purchase_price >= 0", name="purchase_price_non_negative"),
    Index(None, "medicine_id", "expiry_date"),
    Index(None, "batch_number"),
)

# People

patients = Table(
    "patients", metadata, pk(),
    Column("name", Text, nullable=False),
    Column("phone", Text, nullable=False),
    Column("email", Text, nullable=False),
    Column("date_of_birth", Date, nullable=False),
    Column("allergies", ARRAY(Text), nullable=False, server_default=text("'{}'")),
)

prescriptions = Table(
    "prescriptions", metadata, pk(),
    Column("patient_id", UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False),
    Column("prescribed_by", Text, nullable=False),
    ts("date_issued", default=True),
    Column("status", Text, nullable=False, server_default="Active"),
    CheckConstraint("status IN ('Active', 'Fully Dispensed')", name="status_valid"),
    Index("ix_prescriptions_patient_id_date_issued", "patient_id", text("date_issued DESC")),
)

prescription_lines = Table(
    "prescription_lines", metadata, pk(),
    Column("prescription_id", UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("medicine_id", UUID(as_uuid=True), ForeignKey("medicines.id"), nullable=False),
    Column("dosage_instruction", Text, nullable=False),
    Column("duration_days", Integer, nullable=False),
    Column("quantity_prescribed", Integer, nullable=False),
    Column("dispensed_quantity", Integer, nullable=False, server_default="0"),
    UniqueConstraint("prescription_id", "medicine_id"),
    CheckConstraint("quantity_prescribed > 0", name="quantity_positive"),
    # A prescription can never be over-dispensed, whatever the code does
    CheckConstraint("dispensed_quantity >= 0 AND dispensed_quantity <= quantity_prescribed", name="dispensed_in_range"),
)

audit_logs = Table(
    "audit_logs", metadata, pk(),
    ts("timestamp", default=True),
    Column("batch_id", UUID(as_uuid=True), ForeignKey("batches.id"), nullable=False),
    Column("action_type", Text, nullable=False),
    Column("quantity_changed", Integer, nullable=False),
    Column("patient_id", UUID(as_uuid=True)),
    Column("notes", Text, nullable=False, server_default=""),
    Index("ix_audit_logs_timestamp", text('"timestamp" DESC')),
    Index(None, "batch_id"),
)

# Billing

invoice_number_seq = Sequence("invoice_number_seq", start=100001, metadata=metadata)

INVOICE_STATUSES = ("Paid", "Pending", "Partially Paid", "Partially Refunded", "Refunded", "Cancelled")

invoices = Table(
    "invoices", metadata, pk(),
    Column("number", BigInteger, invoice_number_seq, server_default=invoice_number_seq.next_value(),
           nullable=False, unique=True),
    ts("date", default=True),
    Column("patient_id", UUID(as_uuid=True), ForeignKey("patients.id")),
    Column("patient_name", Text, nullable=False),
    Column("patient_phone", Text),
    Column("patient_type", Text, nullable=False),
    Column("doctor_name", Text, nullable=False, server_default=""),
    Column("bill_type", Text, nullable=False),
    Column("payment_method", Text, nullable=False),
    Column("cashier_name", Text, nullable=False),
    Column("store_name", Text, nullable=False),
    Column("gross_amount", MONEY, nullable=False),
    Column("discount_applied", MONEY, nullable=False),
    Column("net_payable", MONEY, nullable=False),
    Column("amount_paid", MONEY, nullable=False),
    Column("balance_due", MONEY, nullable=False),
    Column("refunded_amount", MONEY, nullable=False, server_default="0"),
    Column("cgst", MONEY, nullable=False),
    Column("sgst", MONEY, nullable=False),
    Column("igst", MONEY, nullable=False, server_default="0"),
    Column("total_gst", MONEY, nullable=False),
    Column("gst_inclusive", Boolean, nullable=False, server_default=text("false")),
    Column("status", Text, nullable=False),
    Column("stock_deducted", Boolean, nullable=False, server_default=text("false")),
    Column("prescription_id", UUID(as_uuid=True), ForeignKey("prescriptions.id")),
    Column("duplicated_from", Text),
    ts("cancelled_at", nullable=True),
    Column("cancelled_by", Text),
    Column("amount_paid_before_cancel", MONEY),
    Column("qr_code", Text, nullable=False, server_default=""),
    Column("barcode", Text, nullable=False, server_default=""),
    Column("insurance_details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    CheckConstraint("status IN ('Paid', 'Pending', 'Partially Paid', 'Partially Refunded', 'Refunded', 'Cancelled')",
                    name="status_valid"),
    CheckConstraint("gross_amount >= 0 AND discount_applied >= 0 AND discount_applied <= gross_amount",
                    name="amounts_valid"),
    CheckConstraint("refunded_amount >= 0 AND refunded_amount <= amount_paid OR status = 'Cancelled'",
                    name="refund_within_paid"),
    Index("ix_invoices_date", text("date DESC")),
    Index("ix_invoices_status_date", "status", text("date DESC")),
    Index("ix_invoices_bill_type_date", "bill_type", text("date DESC")),
    Index("ix_invoices_payment_method_date", "payment_method", text("date DESC")),
    Index("ix_invoices_cashier_name_date", "cashier_name", text("date DESC")),
    Index("ix_invoices_patient_id_date", "patient_id", text("date DESC")),
    # Case-insensitive substring search on the ledger
    Index("ix_invoices_patient_name_trgm", "patient_name", postgresql_using="gin",
          postgresql_ops={"patient_name": "gin_trgm_ops"}),
)

invoice_items = Table(
    "invoice_items", metadata, pk(),
    Column("invoice_id", UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("name", Text, nullable=False),
    Column("medicine_id", UUID(as_uuid=True), ForeignKey("medicines.id")),
    Column("batch_id", UUID(as_uuid=True), ForeignKey("batches.id")),
    Column("batch_number", Text, nullable=False, server_default=""),
    Column("quantity", Integer, nullable=False),
    Column("unit_price", MONEY, nullable=False),
    Column("discount", MONEY, nullable=False, server_default="0"),
    Column("gst", MONEY, nullable=False, server_default="0"),
    Column("total_price", MONEY, nullable=False),
    Column("credited_to_prescription", Integer, nullable=False, server_default="0"),
    CheckConstraint("quantity > 0", name="quantity_positive"),
    Index(None, "invoice_id"),
    Index("ix_invoice_items_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
)

invoice_refunds = Table(
    "invoice_refunds", metadata, pk(),
    Column("invoice_id", UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
    Column("amount", MONEY, nullable=False),
    Column("reason", Text, nullable=False),
    Column("approved_by", Text, nullable=False),
    ts("refunded_at", default=True),
    CheckConstraint("amount > 0", name="amount_positive"),
    Index(None, "invoice_id"),
)

invoice_events = Table(
    "invoice_events", metadata, pk(),
    Column("invoice_id", UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
    Column("user_name", Text, nullable=False),
    ts("at", default=True),
    Column("action_type", Text, nullable=False),
    Column("previous_value", Text, nullable=False, server_default=""),
    Column("new_value", Text, nullable=False, server_default=""),
    Index(None, "invoice_id"),
)

# Accounts

users = Table(
    "users", metadata, pk(),
    Column("email", Text, nullable=False),
    Column("full_name", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=text("true")),
    Column("pending_approval", Boolean, nullable=False, server_default=text("false")),
    Column("must_change_password", Boolean, nullable=False, server_default=text("false")),
    Column("failed_login_attempts", Integer, nullable=False, server_default="0"),
    ts("locked_until", nullable=True),
    ts("created_at", default=True),
    ts("updated_at", default=True),
    ts("password_changed_at", default=True),
    ts("last_login_at", nullable=True),
    CheckConstraint("role IN ('admin', 'pharmacist', 'cashier')", name="role_valid"),
    Index("uq_users_email_lower", func.lower(text("email")), unique=True),
)

sessions = Table(
    "sessions", metadata, pk(),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("csrf_token", Text, nullable=False),
    ts("created_at", default=True),
    ts("last_seen_at", default=True),
    ts("expires_at"),
    Column("ip", Text, nullable=False, server_default=""),
    Column("user_agent", Text, nullable=False, server_default=""),
    Index(None, "user_id"),
    Index(None, "expires_at"),
)

auth_events = Table(
    "auth_events", metadata, pk(),
    ts("timestamp", default=True),
    Column("type", Text, nullable=False),
    Column("email", Text, nullable=False, server_default=""),
    Column("user_id", UUID(as_uuid=True)),
    Column("ip", Text, nullable=False, server_default=""),
    Column("user_agent", Text, nullable=False, server_default=""),
    Column("detail", Text, nullable=False, server_default=""),
    Index("ix_auth_events_timestamp", text('"timestamp" DESC')),
)

# Application state (e.g. the demo-data marker)

app_meta = Table(
    "app_meta", metadata,
    Column("key", Text, primary_key=True),
    Column("value", JSONB, nullable=False),
)

# Business data removed by a demo reset (users, sessions and auth events are kept)
BUSINESS_TABLES = ["invoice_events", "invoice_refunds", "invoice_items", "invoices", "audit_logs",
                   "prescription_lines", "prescriptions", "batches", "medicines", "categories", "patients"]
