from datetime import timedelta, timezone
from typing import Any, Dict

from app.modules.billing.service import collected_since
from app.core.common import collected, now_utc
from app.modules.medicines.service import get_all_medicines
from app.modules.medicines import repository as catalog
from app.modules.patients import repository as people


async def get_dashboard_metrics(tz_offset_minutes: int = 0) -> Dict[str, Any]:
    """Headline figures. A fixed handful of queries, whatever the data size."""
    medicines = await get_all_medicines()
    categories = await catalog.list_categories()
    stock_value = await catalog.stock_value_by_medicine()
    dispensed_rx = await people.count_prescriptions_with_dispensing()

    # Revenue comes from invoices, the same source as the financial reports:
    # money collected less refunds, excluding cancelled invoices
    now = now_utc()
    local = timezone(timedelta(minutes=tz_offset_minutes))
    invoices = await collected_since(now - timedelta(days=30))
    total_revenue = round(sum(collected(i) for i in invoices), 2)

    # Daily sales for the last 7 days, in the viewer's local days
    today = now.astimezone(local).date()
    per_day = {today - timedelta(days=i): {"revenue": 0.0, "prescriptions": 0} for i in range(6, -1, -1)}
    for inv in invoices:
        day = inv["date"].astimezone(local).date()
        if day in per_day:
            per_day[day]["revenue"] += collected(inv)
            if inv.get("bill_type") == "Prescription Sale":
                per_day[day]["prescriptions"] += 1
    sales_chart = [{"name": d.strftime("%b %d"), "revenue": round(v["revenue"], 2),
                    "prescriptions": v["prescriptions"]} for d, v in per_day.items()]

    # Medicines and stock value per category
    count_by_cat: Dict[str, int] = {}
    value_by_cat: Dict[str, float] = {}
    for med in medicines:
        cat = med.get("category_id")
        count_by_cat[cat] = count_by_cat.get(cat, 0) + 1
        value_by_cat[cat] = value_by_cat.get(cat, 0.0) + stock_value.get(med["id"], 0.0)
    categories_chart = [{
        "name": cat["name"],
        "value": count_by_cat.get(cat["id"], 0),
        "stock_value": round(value_by_cat.get(cat["id"], 0.0), 2),
        "color": cat["color_code"],
    } for cat in categories]

    return {
        "total_revenue": total_revenue,
        "prescriptions_dispensed": dispensed_rx,
        "active_inventory_value": round(sum(stock_value.values()), 2),
        "low_stock_alerts": sum(1 for m in medicines if m["stock_level_status"] in ("LOW", "OUT_OF_STOCK")),
        "critical_expiry_alerts": sum(1 for m in medicines if m["expiry_status"] == "CRITICAL"),
        "warning_expiry_alerts": sum(1 for m in medicines if m["expiry_status"] == "WARNING"),
        "sales_chart": sales_chart,
        "categories_chart": categories_chart,
    }
