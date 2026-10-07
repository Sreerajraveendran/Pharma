"""Optional demo data.

seed_database() loads demo data (SEED_DEMO_DATA). It only ever seeds an EMPTY database,
  runs in a single transaction (a failed or interrupted seed leaves nothing behind), and
  builds the sales history through the same pricing, invoicing, refund and cancel code as
  the live app, so stock, audit logs, invoices and reports all agree.
"""
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from app.core import config
from app.modules.billing import service as billing_service
from app.db.engine import transaction
from app.modules.pos.service import price_lines
from app.modules.pos import repository as audit
from app.modules.medicines import repository as catalog
from app.db import meta
from app.modules.patients import repository as people

logger = logging.getLogger("app.db.seed")

SEED_VERSION = 3
MARKER_ID = "demo_seed"
RANDOM_SEED = 20240611  # fixed so demo data is reproducible
HISTORY_DAYS = 60


# Demo data entry points

async def demo_seed_status() -> dict:
    marker = await meta.get(MARKER_ID)
    return {"status": marker.get("status"), "version": marker.get("version"),
            "completed_at": marker.get("completed_at")} if marker else {"status": None}


async def seed_database(force_reset: bool = False) -> bool:
    """Loads demo data. Returns True if it seeded.

    Without force_reset it seeds only when no demo seed has completed AND the database
    holds no business data, so it can never mix demo records into real ones. force_reset
    deletes all business data first (the admin demo reset). Wipe, seed and marker commit
    together or not at all.
    """
    async with transaction():
        marker = await meta.get(MARKER_ID)
        if force_reset:
            logger.warning("Demo reset: deleting all business data")
            await meta.wipe_business_data()
        elif marker and marker.get("status") == "complete":
            logger.info("Demo data already seeded. Skipping.")
            return False
        elif await meta.has_business_data():
            logger.info("Database already contains data; not loading demo data.")
            return False

        summary = await _seed_demo_data()
        await meta.put(MARKER_ID, {"status": "complete", "version": SEED_VERSION,
                                   "completed_at": datetime.now(timezone.utc).isoformat(), "summary": summary})
    logger.info(f"Demo data seeded: {summary}")
    return True


# Demo data definitions

CATEGORIES = [
    ("Antibiotics", "#0052cc"),
    ("Analgesics", "#ba1a1a"),
    ("Cardiology", "#006c47"),
    ("Diabetology", "#5e3c00"),
    ("OTC", "#737685"),
    ("Gastroenterology", "#8a4f00"),
    ("Respiratory", "#00658f"),
    ("Vitamins & Supplements", "#5b5f00"),
    ("Dermatology", "#9c2a6b"),
    ("Endocrinology", "#4a4ad0"),
]


def _med(name, generic_name, form, dosage, category, manufacturer, prescription_required, storage_requirement,
         side_effects, min_stock_level, base_uom="Strip") -> dict:
    return {"name": name, "generic_name": generic_name, "form": form, "dosage": dosage, "category": category,
            "manufacturer": manufacturer, "prescription_required": prescription_required,
            "storage_requirement": storage_requirement, "side_effects": side_effects,
            "min_stock_level": min_stock_level, "base_uom": base_uom}


MEDICINES = [
    _med("Augmentin 625 Duo", "Amoxycillin + Clavulanic Acid", "Tablet", "625mg", "Antibiotics", "GlaxoSmithKline", True,
         "Store below 25°C", "Diarrhea, nausea, skin rashes", 50),
    _med("Azithral 500", "Azithromycin", "Tablet", "500mg", "Antibiotics", "Alembic Pharma", True,
         "Store below 30°C", "Nausea, diarrhoea, abdominal pain", 30),
    _med("Ciplox 500", "Ciprofloxacin", "Tablet", "500mg", "Antibiotics", "Cipla", True,
         "Store below 30°C", "Nausea, dizziness, tendon pain", 40),
    _med("Monocef-O 200", "Cefpodoxime Proxetil", "Tablet", "200mg", "Antibiotics", "Aristo Pharma", True,
         "Store below 25°C", "Diarrhoea, headache", 30),
    _med("Crocin 650", "Paracetamol", "Tablet", "650mg", "Analgesics", "GlaxoSmithKline", False,
         "Store in a cool dry place", "Rarely liver damage (in high doses)", 200),
    _med("Dolo 650", "Paracetamol", "Tablet", "650mg", "Analgesics", "Micro Labs", False,
         "Store in a cool dry place", "Rarely liver damage (in high doses)", 250),
    _med("Combiflam", "Ibuprofen + Paracetamol", "Tablet", "400mg/325mg", "Analgesics", "Sanofi India", False,
         "Store below 30°C", "Acidity, stomach pain", 120),
    _med("Zerodol-SP", "Aceclofenac + Paracetamol + Serratiopeptidase", "Tablet", "100mg/325mg/15mg", "Analgesics",
         "Ipca Laboratories", True, "Store below 25°C", "Nausea, heartburn, dizziness", 40),
    _med("Lipitor 20mg", "Atorvastatin", "Tablet", "20mg", "Cardiology", "Pfizer", True,
         "Store below 30°C", "Muscle pain, headache, stuffy nose", 100),
    _med("Telma 40", "Telmisartan", "Tablet", "40mg", "Cardiology", "Glenmark", True,
         "Store below 30°C", "Dizziness, back pain", 60),
    _med("Amlong 5", "Amlodipine", "Tablet", "5mg", "Cardiology", "Micro Labs", True,
         "Store below 30°C", "Ankle swelling, flushing", 60),
    _med("Ecosprin 75", "Aspirin", "Tablet", "75mg", "Cardiology", "USV Pvt Ltd", True,
         "Store in a cool dry place", "Acidity, easy bruising", 100),
    _med("Metformin 500mg", "Metformin Hydrochloride", "Tablet", "500mg", "Diabetology", "USV Pvt Ltd", True,
         "Store below 25°C", "Stomach upset, metallic taste, weakness", 80),
    _med("Glycomet GP 1", "Glimepiride + Metformin", "Tablet", "1mg/500mg", "Diabetology", "USV Pvt Ltd", True,
         "Store below 25°C", "Low blood sugar, nausea", 60),
    _med("Janumet 50/500", "Sitagliptin + Metformin", "Tablet", "50mg/500mg", "Diabetology", "MSD Pharmaceuticals", True,
         "Store below 30°C", "Headache, stomach upset", 20),
    _med("Cetirizine 10mg", "Cetirizine Hydrochloride", "Tablet", "10mg", "OTC", "Dr. Reddy's", False,
         "Store below 30°C", "Drowsiness, dry mouth", 60),
    _med("Digene Antacid", "Magnesium Hydroxide + Simethicone", "Tablet", "Chewable", "OTC", "Abbott", False,
         "Store in a cool dry place", "Mild diarrhea", 40),
    _med("Pan 40", "Pantoprazole", "Tablet", "40mg", "Gastroenterology", "Alkem Laboratories", True,
         "Store below 25°C", "Headache, flatulence", 80),
    _med("Omez 20", "Omeprazole", "Capsule", "20mg", "Gastroenterology", "Dr. Reddy's", True,
         "Store below 25°C", "Headache, abdominal pain", 50),
    _med("Electral ORS", "Oral Rehydration Salts", "Powder", "21.8g sachet", "Gastroenterology", "FDC Ltd", False,
         "Store in a cool dry place", "Rarely vomiting", 100, "Sachet"),
    _med("Montair LC", "Montelukast + Levocetirizine", "Tablet", "10mg/5mg", "Respiratory", "Cipla", True,
         "Store below 25°C", "Drowsiness, headache", 40),
    _med("Asthalin Inhaler", "Salbutamol", "Inhaler", "100mcg/dose", "Respiratory", "Cipla", True,
         "Store below 30°C, do not freeze", "Tremor, palpitations", 10, "Unit"),
    _med("Benadryl Cough Syrup", "Diphenhydramine + Ammonium Chloride", "Syrup", "100ml", "Respiratory",
         "Johnson & Johnson", False, "Store below 25°C", "Drowsiness, dry mouth", 25, "Bottle"),
    _med("Becosules", "Vitamin B-Complex + Vitamin C", "Capsule", "Multivitamin", "Vitamins & Supplements", "Pfizer",
         False, "Store in a cool dry place", "Rarely nausea", 80),
    _med("Shelcal 500", "Calcium Carbonate + Vitamin D3", "Tablet", "500mg/250IU", "Vitamins & Supplements",
         "Torrent Pharma", False, "Store below 30°C", "Constipation, bloating", 60),
    _med("Limcee 500", "Vitamin C (Ascorbic Acid)", "Tablet", "500mg chewable", "Vitamins & Supplements", "Abbott",
         False, "Store in a cool dry place", "Rarely stomach upset", 60),
    _med("Candid Cream", "Clotrimazole", "Cream", "1% w/w, 20g", "Dermatology", "Glenmark", False,
         "Store below 30°C", "Local irritation, burning", 20, "Tube"),
    _med("Betnovate-N", "Betamethasone + Neomycin", "Cream", "0.1%/0.5%, 20g", "Dermatology", "GlaxoSmithKline", True,
         "Store below 25°C", "Skin thinning with long use", 20, "Tube"),
    _med("Thyronorm 50", "Levothyroxine", "Tablet", "50mcg", "Endocrinology", "Abbott", True,
         "Store below 25°C, protect from light", "Palpitations if overdosed", 20, "Bottle"),
]

# (medicine, batch number, days to expiry, stock on hand TODAY, purchase price, MRP)
# Today's stock shows every alert the app knows: Augmentin has a batch expiring in 15 days
# and Benadryl an expired one awaiting return (CRITICAL); Dolo and Limcee expire within
# six months (WARNING); Metformin, Janumet and Asthalin are below their minimum (LOW);
# Pan 40 is sold out (OUT_OF_STOCK).
BATCHES = [
    ("Augmentin 625 Duo", "AUG920", 250, 120, 80.00, 120.00),
    ("Augmentin 625 Duo", "AUG112", 15, 40, 75.00, 110.00),
    ("Azithral 500", "AZI231", 410, 64, 92.00, 119.50),
    ("Ciplox 500", "CIP557", 300, 85, 30.00, 41.20),
    ("Monocef-O 200", "MON419", 220, 48, 84.00, 109.00),
    ("Crocin 650", "CRO322", 500, 450, 10.00, 15.00),
    ("Dolo 650", "DOL771", 540, 380, 23.00, 33.60),
    ("Dolo 650", "DOL702", 95, 140, 22.50, 33.60),
    ("Combiflam", "CMB318", 480, 160, 32.00, 44.00),
    ("Zerodol-SP", "ZER640", 260, 52, 82.00, 110.00),
    ("Lipitor 20mg", "LIP803", 400, 180, 30.00, 45.00),
    ("Telma 40", "TEL905", 380, 90, 190.00, 262.00),
    ("Amlong 5", "AML214", 450, 110, 36.00, 51.50),
    ("Ecosprin 75", "ECO083", 600, 240, 3.80, 5.60),
    ("Metformin 500mg", "MET404", 120, 20, 8.00, 12.00),
    ("Glycomet GP 1", "GLY366", 330, 95, 80.00, 110.70),
    ("Janumet 50/500", "JAN128", 290, 8, 360.00, 482.00),
    ("Cetirizine 10mg", "CET118", 300, 95, 18.00, 32.00),
    ("Digene Antacid", "DIG560", 75, 55, 22.00, 38.00),
    ("Pan 40", "PAN447", 350, 0, 115.00, 158.00),
    ("Omez 20", "OMZ512", 240, 70, 42.00, 59.80),
    ("Electral ORS", "ELE690", 700, 210, 16.00, 22.00),
    ("Montair LC", "MTR733", 310, 46, 170.00, 232.00),
    ("Asthalin Inhaler", "AST290", 400, 4, 105.00, 145.50),
    ("Benadryl Cough Syrup", "BEN155", 180, 34, 88.00, 121.00),
    ("Benadryl Cough Syrup", "BEN092", -6, 12, 85.00, 118.00),
    ("Becosules", "BEC860", 520, 150, 34.00, 47.90),
    ("Shelcal 500", "SHL341", 420, 88, 88.00, 124.00),
    ("Limcee 500", "LIM578", 160, 130, 18.00, 25.10),
    ("Candid Cream", "CAN223", 640, 38, 62.00, 85.00),
    ("Betnovate-N", "BET467", 500, 27, 22.00, 31.50),
    ("Thyronorm 50", "THY619", 360, 26, 130.00, 181.00),
]
# By batch-number prefix
SUPPLIERS = {"AUG": "supp_01", "AZI": "supp_05", "CIP": "supp_02", "MON": "supp_05", "CRO": "supp_01",
             "DOL": "supp_03", "CMB": "supp_04", "ZER": "supp_06", "LIP": "supp_02", "TEL": "supp_06",
             "AML": "supp_03", "ECO": "supp_03", "MET": "supp_03", "GLY": "supp_03", "JAN": "supp_02",
             "CET": "supp_04", "DIG": "supp_04", "PAN": "supp_06", "OMZ": "supp_05", "ELE": "supp_04",
             "MTR": "supp_02", "AST": "supp_02", "BEN": "supp_04", "BEC": "supp_01", "SHL": "supp_06",
             "LIM": "supp_04", "CAN": "supp_05", "BET": "supp_01", "THY": "supp_06"}
LOCATIONS = {"AUG": "Aisle 4, Shelf B", "AZI": "Aisle 4, Shelf A", "CIP": "Aisle 4, Shelf C", "MON": "Aisle 4, Shelf D",
             "CRO": "Aisle 1, Shelf C", "DOL": "Aisle 1, Shelf D", "CMB": "Aisle 1, Shelf E", "ZER": "Aisle 5, Shelf A",
             "LIP": "Aisle 2, Shelf A", "TEL": "Aisle 2, Shelf B", "AML": "Aisle 2, Shelf C", "ECO": "Aisle 2, Shelf D",
             "MET": "Aisle 3, Shelf D", "GLY": "Aisle 3, Shelf A", "JAN": "Aisle 3, Shelf B", "CET": "Aisle 1, Shelf A",
             "DIG": "Aisle 1, Shelf B", "PAN": "Aisle 5, Shelf B", "OMZ": "Aisle 5, Shelf C", "ELE": "Counter, Rack 1",
             "MTR": "Aisle 6, Shelf A", "AST": "Aisle 6, Shelf B", "BEN": "Counter, Rack 2", "BEC": "Aisle 7, Shelf A",
             "SHL": "Aisle 7, Shelf B", "LIM": "Counter, Rack 3", "CAN": "Aisle 8, Shelf A", "BET": "Aisle 8, Shelf B",
             "THY": "Cold Room, Shelf 1"}


def _patient(name, phone, date_of_birth, allergies=()) -> dict:
    return {"name": name, "phone": phone, "email": name.lower().replace(" ", ".") + "@example.com",
            "date_of_birth": date_of_birth, "allergies": list(allergies)}


# John Doe and Jane Smith are referenced by the tests; each has one open prescription
PATIENTS = [
    _patient("John Doe", "+91 98450 10199", "1985-05-15", ["Penicillin"]),
    _patient("Jane Smith", "+91 98450 10245", "1990-08-20"),
    _patient("Aarav Sharma", "+91 99001 23456", "1978-02-11"),
    _patient("Priya Nair", "+91 98860 44120", "1992-11-03", ["Sulfa drugs"]),
    _patient("Rohan Mehta", "+91 97400 55812", "1965-07-29"),
    _patient("Ananya Iyer", "+91 99450 67023", "2001-04-17"),
    _patient("Vikram Singh", "+91 98100 78934", "1958-09-05", ["Aspirin"]),
    _patient("Meera Pillai", "+91 94470 89345", "1987-12-22"),
    _patient("Aditya Kulkarni", "+91 98220 31457", "1983-03-09"),
    _patient("Sneha Reddy", "+91 99630 21784", "1995-06-14", ["Penicillin"]),
    _patient("Karthik Subramanian", "+91 94440 58213", "1971-10-02"),
    _patient("Fatima Sheikh", "+91 98199 64320", "1988-01-25"),
    _patient("Rajesh Patel", "+91 98250 77341", "1962-08-18", ["Sulfa drugs"]),
    _patient("Divya Menon", "+91 94950 13862", "1999-12-07"),
    _patient("Arjun Das", "+91 98300 46219", "1975-04-30"),
    _patient("Lakshmi Krishnan", "+91 94431 70528", "1955-02-13", ["Aspirin"]),
    _patient("Nikhil Joshi", "+91 97690 38146", "1991-09-21"),
    _patient("Pooja Agarwal", "+91 98290 52673", "1986-07-08"),
    _patient("Mohammed Irfan", "+91 99860 27495", "1980-11-16"),
    _patient("Kavya Hegde", "+91 99016 84372", "2003-05-27"),
    _patient("Sanjay Bhatia", "+91 98110 63984", "1968-03-03", ["Ibuprofen"]),
    _patient("Neha Kapoor", "+91 98715 40236", "1993-10-19"),
    _patient("Ramesh Gowda", "+91 94480 91527", "1959-06-11"),
    _patient("Shalini Varma", "+91 94460 35718", "1984-01-30"),
    _patient("Thomas Mathew", "+91 94470 26193", "1972-12-24"),
    _patient("Ishaan Malhotra", "+91 98180 74651", "2008-08-02"),
    _patient("Deepa Raghavan", "+91 98404 19837", "1979-05-05", ["Penicillin"]),
    _patient("Harish Chandra", "+91 94150 68324", "1950-09-14"),
    _patient("Swati Deshpande", "+91 98230 57196", "1997-03-28"),
    _patient("Gaurav Saxena", "+91 98390 41768", "1989-11-09"),
]
# Medicines never sold or prescribed to a patient with the allergy
ALLERGY_CONFLICTS = {"Penicillin": {"Augmentin 625 Duo"}, "Aspirin": {"Ecosprin 75"}, "Ibuprofen": {"Combiflam"}}

DOCTORS = ["Dr. Sarah Jenkins", "Dr. Alex Carter", "Dr. Kavita Rao", "Dr. Arjun Menon", "Dr. Fatima Qureshi",
           "Dr. Rajiv Bose"]
CASHIERS = ["Rahul Verma", "Anjali Gupta", "Suresh Kumar", "Deepika Rao"]
PHARMACIST = "Meera Krishnan"  # approves demo refunds and cancellations
DOSAGE_BY_MEDICINE = {
    "Augmentin 625 Duo": "1 tablet twice daily after food",
    "Azithral 500": "1 tablet daily for 3 days",
    "Ciplox 500": "1 tablet twice daily",
    "Monocef-O 200": "1 tablet twice daily after food",
    "Zerodol-SP": "1 tablet twice daily after food",
    "Lipitor 20mg": "1 tablet daily at bedtime",
    "Telma 40": "1 tablet daily in the morning",
    "Amlong 5": "1 tablet daily",
    "Ecosprin 75": "1 tablet daily after lunch",
    "Metformin 500mg": "1 tablet daily after breakfast",
    "Glycomet GP 1": "1 tablet before breakfast",
    "Janumet 50/500": "1 tablet twice daily with meals",
    "Pan 40": "1 tablet daily before breakfast",
    "Omez 20": "1 capsule daily before breakfast",
    "Montair LC": "1 tablet daily at bedtime",
    "Asthalin Inhaler": "2 puffs when needed for breathlessness",
    "Betnovate-N": "Apply thinly twice daily",
    "Thyronorm 50": "1 tablet daily on an empty stomach",
}
SALES_TODAY = 14  # sales scheduled through today; those already in the past are created


def _allowed(patient, names: List[str]) -> List[str]:
    blocked = set().union(*(ALLERGY_CONFLICTS.get(a, set()) for a in (patient or {}).get("allergies", [])))
    return [n for n in names if n not in blocked]


async def _seed_demo_data() -> Dict[str, int]:
    rng = random.Random(RANDOM_SEED)
    now = datetime.now(timezone.utc)

    # 1. Catalogue
    cat_ids = {}
    for name, color in CATEGORIES:
        cat_ids[name] = (await catalog.insert_category({"name": name, "color_code": color}))["id"]

    meds = {}
    for m in MEDICINES:
        doc = {k: v for k, v in m.items() if k != "category"}
        doc["category_id"] = cat_ids[m["category"]]
        meds[m["name"]] = await catalog.insert_medicine(doc)

    batches = []
    for med_name, number, days, on_hand, cost, mrp in BATCHES:
        doc = {"medicine_id": meds[med_name]["id"], "batch_number": number,
               "expiry_date": now + timedelta(days=days), "quantity_on_hand": on_hand,
               "supplier_id": SUPPLIERS[number[:3]], "location_code": LOCATIONS[number[:3]],
               "purchase_price": cost, "mrp": mrp}
        batches.append({**await catalog.insert_batch(doc), "medicine_name": med_name})

    def fefo_batch(med_name: str, at: datetime) -> dict:
        # First-expiry-first-out among batches that were still in date at sale time
        usable = [b for b in batches if b["medicine_name"] == med_name and b["expiry_date"] > at]
        return min(usable, key=lambda b: b["expiry_date"])

    # 2. Patients
    patients = []
    for p in PATIENTS:
        patients.append(await people.insert_patient(p))
    john, jane = patients[0], patients[1]
    regulars = patients[2:]

    # 3. Open prescriptions (inserted first so they're found first by name-based lookups)
    for rx in [
        {"patient_id": john["id"], "prescribed_by": "Dr. Sarah Jenkins", "date_issued": now - timedelta(days=2),
         "status": "Active", "medicines": [{"medicine_id": meds["Metformin 500mg"]["id"],
                                            "dosage_instruction": "1 tablet daily after breakfast",
                                            "duration_days": 30, "quantity_prescribed": 30, "dispensed_quantity": 0}]},
        {"patient_id": jane["id"], "prescribed_by": "Dr. Alex Carter", "date_issued": now - timedelta(days=1),
         "status": "Active", "medicines": [{"medicine_id": meds["Crocin 650"]["id"],
                                            "dosage_instruction": "1 tablet thrice daily as needed",
                                            "duration_days": 5, "quantity_prescribed": 15, "dispensed_quantity": 0}]},
    ]:
        await people.insert_prescription(rx)

    rx_meds = [n for n, m in meds.items() if m["prescription_required"]]
    otc_meds = [n for n, m in meds.items() if not m["prescription_required"]]
    invoices: List[dict] = []
    audit_logs: List[dict] = []

    async def sell(r: random.Random, at: datetime, recent: bool) -> dict:
        """One sale at `at`, priced and invoiced through the live code paths."""
        is_rx_sale = r.random() < 0.35
        patient = r.choice(regulars) if is_rx_sale or r.random() < 0.3 else None
        if is_rx_sale:
            names = r.sample(_allowed(patient, rx_meds), r.randint(1, 2))
            if r.random() < 0.4:
                names.append(r.choice(_allowed(patient, otc_meds)))  # an OTC item bought alongside
        else:
            names = r.sample(_allowed(patient, otc_meds), r.randint(1, 3))

        lines = []
        for name in names:
            batch = fefo_batch(name, at)
            lines.append({"batch_id": batch["id"], "medicine_id": meds[name]["id"], "name": name,
                          "batch_number": batch["batch_number"], "quantity": r.randint(1, 4), "mrp": batch["mrp"]})

        rx_id, doctor = None, ""
        if is_rx_sale:
            doctor = r.choice(DOCTORS)
            prescribed = [l for l in lines if meds[l["name"]]["prescription_required"]]
            for l in prescribed:
                l["credit"] = l["quantity"]
            # Recent prescriptions are sometimes only partly dispensed and stay open
            extra = r.randint(2, 10) if r.random() < 0.3 and recent else 0
            rx = await people.insert_prescription({
                "patient_id": patient["id"], "prescribed_by": doctor,
                "date_issued": at - timedelta(hours=r.randint(1, 48)),
                "status": "Active" if extra else "Fully Dispensed",
                "medicines": [{"medicine_id": l["medicine_id"], "dosage_instruction": DOSAGE_BY_MEDICINE[l["name"]],
                               "duration_days": (l["quantity"] + extra) * 5,
                               "quantity_prescribed": l["quantity"] + extra,
                               "dispensed_quantity": l["quantity"]} for l in prescribed],
            })
            rx_id = rx["id"]

        items, gross, discount = price_lines(lines, r.choices([0, 5, 10], weights=[70, 20, 10])[0])
        cashier = r.choice(CASHIERS)
        inv = await billing_service.insert_invoice({
            "patient_id": patient["id"] if patient else None,
            "patient_name": patient["name"] if patient else "Walk-in Customer",
            "patient_phone": patient["phone"] if patient else None,
            "patient_type": "Registered" if patient else "Walk-in",
            "doctor_name": doctor,
            "bill_type": "Prescription Sale" if is_rx_sale else "POS Sale",
            "payment_method": r.choices(["Cash", "Card", "UPI"], weights=[35, 20, 45])[0],
            "gross_amount": gross,
            "discount_applied": discount,
            "billing_items": items,
            "cashier_name": cashier,
            "store_name": config.STORE_NAME,
            "stock_deducted": True,
            "prescription_id": rx_id,
        }, inclusive_tax=True, paid=True, actor=cashier, at=at)
        invoices.append(inv)
        audit_logs.extend({
            "timestamp": at, "batch_id": l["batch_id"], "action_type": "Sale",
            "quantity_changed": -l["quantity"], "patient_id": patient["id"] if patient else None,
            "notes": f"POS Checkout {inv['id']}",
        } for l in lines)
        return inv

    # 4. Sales history: whole days ending yesterday, oldest first so invoice numbers follow
    # dates. Busier at weekends. Whole days keep the number of sales (and every random draw
    # after them) independent of the time of day the seed runs.
    sale_times = []
    for day in range(HISTORY_DAYS, 0, -1):
        day_start = (now - timedelta(days=day)).replace(hour=3, minute=30, second=0, microsecond=0)  # 09:00 IST
        weekend = (day_start + timedelta(hours=5, minutes=30)).weekday() >= 5
        for _ in range(rng.randint(11, 16) if weekend else rng.randint(8, 12)):
            sale_times.append((day_start + timedelta(minutes=rng.randint(0, 12 * 60)), day <= 21))  # until 21:00 IST
    sale_times.sort()
    for at, recent in sale_times:
        await sell(rng, at, recent)

    # 5. After-sale events, through the same service code as the Reports screen
    refunds = 0
    cancelled = set()
    for inv in list(invoices):
        roll = rng.random()
        later = min(inv["date"] + timedelta(hours=rng.randint(1, 30)), now - timedelta(minutes=1))
        if roll < 0.03:
            amount = inv["net_payable"] if rng.random() < 0.5 else round(inv["net_payable"] * rng.uniform(0.2, 0.6), 2)
            await billing_service.process_refund(inv["id"], amount, rng.choice(
                ["Patient returned unopened strip", "Wrong strength dispensed", "Billing error"]), PHARMACIST, at=later)
            refunds += 1
        elif roll < 0.05 and inv["bill_type"] == "POS Sale":
            # Cancelled sales put their stock back. Take it off first so today's stock
            # still ends at the BATCHES figures after the cancellation returns it.
            for item in inv["billing_items"]:
                await catalog.restock(item["batch_id"], -item["quantity"])
            await billing_service.cancel_invoice(inv["id"], PHARMACIST, at=later)
            cancelled.add(inv["id"])

    # 6. Today's trading so far, so the dashboard and "today" figures are live. A separate
    # generator keeps the history above identical whatever the time of day.
    today = random.Random(RANDOM_SEED + 1)
    day_start = now.replace(hour=3, minute=30, second=0, microsecond=0)
    for at in sorted(day_start + timedelta(minutes=today.randint(0, 12 * 60)) for _ in range(SALES_TODAY)):
        if at < now - timedelta(minutes=2):
            await sell(today, at, True)

    # 7. A few new prescriptions waiting to be dispensed
    for days_ago, patient in zip((1, 2, 3, 5), rng.sample(regulars, 4)):
        names = rng.sample(_allowed(patient, rx_meds), rng.randint(1, 3))
        await people.insert_prescription({
            "patient_id": patient["id"], "prescribed_by": rng.choice(DOCTORS),
            "date_issued": now - timedelta(days=days_ago, hours=rng.randint(0, 8)), "status": "Active",
            "medicines": [{"medicine_id": meds[n]["id"], "dosage_instruction": DOSAGE_BY_MEDICINE[n],
                           "duration_days": 30, "quantity_prescribed": rng.choice([10, 14, 15, 30]),
                           "dispensed_quantity": 0} for n in names],
        })

    # 8. Goods receipts: each batch arrived before the history began, with what was sold
    # since (less cancelled returns) plus today's stock
    sold: Dict[str, int] = {}
    for inv in invoices:
        if inv["id"] not in cancelled:
            for item in inv["billing_items"]:
                sold[item["batch_id"]] = sold.get(item["batch_id"], 0) + item["quantity"]
    history_start = now - timedelta(days=HISTORY_DAYS)
    receipts = [{
        "timestamp": history_start - timedelta(days=rng.randint(3, 20), hours=rng.randint(0, 8)),
        "batch_id": b["id"], "action_type": "Stock In", "patient_id": None,
        "quantity_changed": b["quantity_on_hand"] + sold.get(b["id"], 0),
        "notes": f"Received from {b['supplier_id']} (GRN-{2400 + i})",
    } for i, b in enumerate(batches)]
    await audit.insert_logs([r for r in receipts if r["quantity_changed"] > 0] + audit_logs)

    return {"medicines": len(meds), "batches": len(batches), "patients": len(patients),
            "invoices": len(invoices), "refunds": refunds, "cancellations": len(cancelled),
            "audit_logs": len(audit_logs) + len(receipts)}
