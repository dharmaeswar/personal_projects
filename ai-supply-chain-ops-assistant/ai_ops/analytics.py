"""Analytics over seeded inventory data for a retailer's fulfillment network.

All numbers are recomputed from the seeded data on every call, and every
answer names the method used, so an operator can check the figure instead
of trusting it. Data is synthetic and seeded for demonstration.
"""

# Seeded inventory: sku, warehouse, on-hand units, avg daily demand,
# demand std-dev, lead time in days, unit cost in dollars.
INVENTORY = [
    {"sku": "PET-FOOD-001", "warehouse": "FC-NORTH", "on_hand": 120, "daily_demand": 40, "demand_std": 8, "lead_time_days": 3, "unit_cost": 24.99},
    {"sku": "PET-FOOD-001", "warehouse": "FC-SOUTH", "on_hand": 15, "daily_demand": 35, "demand_std": 7, "lead_time_days": 3, "unit_cost": 24.99},
    {"sku": "PET-TOY-014", "warehouse": "FC-NORTH", "on_hand": 0, "daily_demand": 12, "demand_std": 4, "lead_time_days": 5, "unit_cost": 9.99},
    {"sku": "PET-TOY-014", "warehouse": "FC-SOUTH", "on_hand": 220, "daily_demand": 10, "demand_std": 3, "lead_time_days": 5, "unit_cost": 9.99},
    {"sku": "PET-BED-022", "warehouse": "FC-NORTH", "on_hand": 60, "daily_demand": 6, "demand_std": 2, "lead_time_days": 7, "unit_cost": 49.99},
    {"sku": "PET-BED-022", "warehouse": "FC-SOUTH", "on_hand": 45, "daily_demand": 5, "demand_std": 2, "lead_time_days": 7, "unit_cost": 49.99},
    {"sku": "PET-TREAT-030", "warehouse": "FC-NORTH", "on_hand": 8, "daily_demand": 25, "demand_std": 6, "lead_time_days": 2, "unit_cost": 6.49},
    {"sku": "PET-TREAT-030", "warehouse": "FC-SOUTH", "on_hand": 90, "daily_demand": 22, "demand_std": 5, "lead_time_days": 2, "unit_cost": 6.49},
]

# Seeded open orders: order id, sku, warehouse, promised delivery day,
# order value in dollars, carrier lane.
ORDERS = [
    {"order_id": "ORD-1001", "sku": "PET-FOOD-001", "warehouse": "FC-SOUTH", "promised_day": 2, "value": 89.99, "lane": "LANE-A"},
    {"order_id": "ORD-1002", "sku": "PET-TOY-014", "warehouse": "FC-NORTH", "promised_day": 1, "value": 19.98, "lane": "LANE-B"},
    {"order_id": "ORD-1003", "sku": "PET-TREAT-030", "warehouse": "FC-NORTH", "promised_day": 3, "value": 32.45, "lane": "LANE-A"},
    {"order_id": "ORD-1004", "sku": "PET-BED-022", "warehouse": "FC-SOUTH", "promised_day": 5, "value": 149.97, "lane": "LANE-A"},
]


def days_of_cover(row):
    """Days until on-hand stock runs out at average daily demand."""
    if row["daily_demand"] <= 0:
        return float("inf")
    return round(row["on_hand"] / row["daily_demand"], 1)


def reorder_point(row, service_factor=1.65):
    """Reorder point = avg daily demand x lead time + safety stock.

    Safety stock = 1.65 x std-dev of daily demand x sqrt(lead time),
    covering about 95% of demand variation (see runbook RB-REORDER-03).
    """
    safety = service_factor * row["demand_std"] * (row["lead_time_days"] ** 0.5)
    return round(row["daily_demand"] * row["lead_time_days"] + safety, 1)


def fill_rate():
    """Share of seeded order lines that can be filled from on-hand stock."""
    filled = 0
    for order in ORDERS:
        stock = next(
            (r for r in INVENTORY
             if r["sku"] == order["sku"] and r["warehouse"] == order["warehouse"]),
            None,
        )
        if stock is not None and stock["on_hand"] > 0:
            filled += 1
    return round(filled / len(ORDERS), 3) if ORDERS else 0.0


def stockouts():
    """Inventory rows with zero on-hand stock."""
    return [dict(r, days_of_cover=0.0) for r in INVENTORY if r["on_hand"] == 0]


def low_cover(threshold_days=7):
    """Rows with less than threshold_days of cover, worst first."""
    rows = [
        dict(r, days_of_cover=days_of_cover(r), reorder_point=reorder_point(r))
        for r in INVENTORY
        if r["on_hand"] > 0
    ]
    rows = [r for r in rows if r["days_of_cover"] < threshold_days]
    rows.sort(key=lambda r: r["days_of_cover"])
    return rows


def at_risk_orders(lane, delay_hours):
    """Orders on a delayed lane whose promised day falls in the delay window.

    Follows runbook RB-CARRIER-04: orders are at risk when the delay window
    reaches their promised delivery day; reroute is only suggested when the
    delay exceeds 72 hours and the order value is above $75.
    """
    window_days = delay_hours / 24.0
    at_risk = []
    for order in ORDERS:
        if order["lane"] != lane:
            continue
        if order["promised_day"] <= window_days:
            at_risk.append({
                **order,
                "reroute_suggested": delay_hours > 72 and order["value"] > 75,
            })
    return at_risk


def answer(question):
    """Answer a data question with recomputed numbers and the method used."""
    q = question.lower()
    if "fill rate" in q:
        rate = fill_rate()
        return {
            "question": question,
            "answer": f"Fill rate is {rate * 100:.1f}% — {int(rate * len(ORDERS))} of {len(ORDERS)} open order lines can be filled from on-hand stock.",
            "value": rate,
            "method": "Counted open order lines with on-hand stock above zero at the assigned warehouse, divided by all open order lines.",
        }
    if "stockout" in q:
        rows = stockouts()
        names = ", ".join(f"{r['sku']} at {r['warehouse']}" for r in rows) or "none"
        return {
            "question": question,
            "answer": f"{len(rows)} stockout(s): {names}.",
            "value": [f"{r['sku']}@{r['warehouse']}" for r in rows],
            "method": "Inventory rows with on-hand stock equal to zero.",
        }
    if "cover" in q or "low stock" in q:
        rows = low_cover()
        detail = "; ".join(
            f"{r['sku']} at {r['warehouse']}: {r['days_of_cover']} days of cover, reorder point {r['reorder_point']}"
            for r in rows
        ) or "no rows under 7 days of cover"
        return {
            "question": question,
            "answer": f"Low-cover rows (under 7 days): {detail}.",
            "value": rows,
            "method": "Days of cover = on-hand units divided by average daily demand; reorder point per runbook RB-REORDER-03.",
        }
    return {
        "question": question,
        "answer": (
            "I can answer fill rate, stockouts, and days of cover from the "
            "seeded inventory data. Please ask one of those."
        ),
        "value": None,
        "method": "No matching analytics question.",
    }
