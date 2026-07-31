"""The feature being released: "Order Insights v2".

This module holds BOTH code paths side by side:

* `legacy_view()` — the version customers use today. Known good. Boring.
* `v2_view()`     — the new version we want to ship faster without adding risk.

`build_view(flag_on)` picks between them. Nothing in this file knows that
LaunchDarkly exists — the flag decision is made in app.py and handed down as a
plain boolean. Keeping the flag check at the edge like this is deliberate: the
feature code stays testable, and when the release is finished you delete one
branch and the flag, not a web of SDK calls.

The order data is a hard-coded, deterministic stand-in for whatever your real
data source would be.
"""

from datetime import date, timedelta

# --- Sample data ------------------------------------------------------------
# Fixed, ordered newest-first. Replace with a real query in a real application.
_TODAY = date(2026, 3, 16)

_ORDERS = [
    # (id,      customer,             region,   amount,   status,        days_to_fulfil, days_ago)
    ("ORD-4821", "Northwind Trading", "EMEA", 18420.00, "Fulfilled", 2, 0),
    ("ORD-4820", "Harborlight Supply", "AMER", 2380.50, "Fulfilled", 1, 0),
    ("ORD-4819", "Kestrel Robotics", "APAC", 44190.00, "Processing", None, 1),
    ("ORD-4818", "Bluefin Logistics", "AMER", 9075.25, "Fulfilled", 4, 2),
    ("ORD-4817", "Northwind Trading", "EMEA", 12610.00, "Delayed", None, 3),
    ("ORD-4816", "Sable & Co.", "AMER", 1590.00, "Fulfilled", 1, 4),
    ("ORD-4815", "Kestrel Robotics", "APAC", 38750.00, "Fulfilled", 3, 6),
    ("ORD-4814", "Meridian Foods", "EMEA", 7320.75, "Delayed", None, 8),
    ("ORD-4813", "Bluefin Logistics", "AMER", 15980.00, "Fulfilled", 2, 9),
    ("ORD-4812", "Harborlight Supply", "AMER", 4410.00, "Fulfilled", 5, 11),
    ("ORD-4811", "Sable & Co.", "AMER", 2265.00, "Fulfilled", 2, 13),
    ("ORD-4810", "Meridian Foods", "EMEA", 21040.00, "Fulfilled", 3, 15),
    ("ORD-4809", "Kestrel Robotics", "APAC", 33500.00, "Fulfilled", 4, 18),
    ("ORD-4808", "Northwind Trading", "EMEA", 8890.00, "Fulfilled", 2, 21),
    ("ORD-4807", "Bluefin Logistics", "AMER", 6120.00, "Fulfilled", 6, 24),
    ("ORD-4806", "Harborlight Supply", "AMER", 3745.50, "Fulfilled", 3, 27),
]


def _orders() -> list[dict]:
    return [
        {
            "id": o[0],
            "customer": o[1],
            "region": o[2],
            "amount": o[3],
            "status": o[4],
            "days_to_fulfil": o[5],
            "placed_on": _TODAY - timedelta(days=o[6]),
            "days_ago": o[6],
        }
        for o in _ORDERS
    ]


# --- Version 1: what customers use today ------------------------------------


def legacy_view() -> dict:
    """The current, already-released Order Insights panel: a plain table."""
    orders = _orders()
    recent = orders[:6]
    return {
        "variant": "legacy",
        "title": "Order Insights",
        "subtitle": "Your six most recent orders.",
        "orders": recent,
        "total_orders": len(orders),
        "total_value": sum(o["amount"] for o in orders),
    }


# --- Version 2: the new feature we are releasing ----------------------------


def v2_view() -> dict:
    """The new Order Insights: trends, regional split, and risk detection."""
    orders = _orders()

    fulfilled = [o for o in orders if o["days_to_fulfil"] is not None]
    at_risk = [o for o in orders if o["status"] == "Delayed"]

    # Revenue bucketed into the last four 7-day windows, oldest window first.
    weeks = []
    for week_index in range(3, -1, -1):
        lo, hi = week_index * 7, week_index * 7 + 7
        bucket = [o for o in orders if lo <= o["days_ago"] < hi]
        weeks.append(
            {
                "label": "This week" if week_index == 0 else f"{week_index}w ago",
                "revenue": sum(o["amount"] for o in bucket),
                "count": len(bucket),
            }
        )
    peak_revenue = max((w["revenue"] for w in weeks), default=0) or 1
    for week in weeks:
        # Percentage height for the CSS bar chart.
        week["height_pct"] = round(week["revenue"] / peak_revenue * 100)

    # Revenue by region, largest first.
    by_region: dict[str, dict] = {}
    total_value = sum(o["amount"] for o in orders)
    for order in orders:
        entry = by_region.setdefault(order["region"], {"region": order["region"], "revenue": 0.0, "count": 0})
        entry["revenue"] += order["amount"]
        entry["count"] += 1
    regions = sorted(by_region.values(), key=lambda r: r["revenue"], reverse=True)
    for region in regions:
        region["share_pct"] = round(region["revenue"] / total_value * 100)

    this_week, last_week = weeks[-1]["revenue"], weeks[-2]["revenue"]
    change_pct = round((this_week - last_week) / last_week * 100) if last_week else 0

    return {
        "variant": "v2",
        "title": "Order Insights",
        "subtitle": "Revenue trend, regional performance, and orders that need attention.",
        "total_orders": len(orders),
        "total_value": total_value,
        "avg_fulfilment_days": round(sum(o["days_to_fulfil"] for o in fulfilled) / len(fulfilled), 1),
        "week_over_week_pct": change_pct,
        "weeks": weeks,
        "regions": regions,
        "at_risk": at_risk,
        "at_risk_value": sum(o["amount"] for o in at_risk),
    }


def build_view(flag_on: bool) -> dict:
    """Return the view model for whichever version of the feature is live.

    `flag_on` comes straight from the LaunchDarkly evaluation in app.py.
    """
    return v2_view() if flag_on else legacy_view()
