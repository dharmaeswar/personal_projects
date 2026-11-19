"""Source adapters.

Each adapter reads one partner's raw feed and yields plain dicts.
Adapters do no cleaning: mapping and validation happen in normalize.py and
quality.py, so a bad source row is visible instead of silently fixed.
Supported shapes mirror the JD: APIs/webhooks (JSON), polling (JSON),
SFTP files (CSV), and queues (JSON lines).
"""

from __future__ import annotations

import csv
import io
import json
from typing import Iterable


def read_device_telemetry_jsonl(text: str) -> list[dict]:
    """Device telemetry arriving as JSON lines (API / webhook / queue)."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def read_carrier_milestones_csv(text: str) -> list[dict]:
    """Carrier milestones arriving as a CSV file (SFTP drop)."""
    return list(csv.DictReader(io.StringIO(text)))


def read_customer_orders_json(text: str) -> list[dict]:
    """Customer order data arriving as a JSON array (API poll)."""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("customer orders feed must be a JSON array")
    return data


def generate_synthetic_feeds(seed: int = 42) -> dict[str, str]:
    """Deterministic synthetic feeds for a demo run and for tests.

    240 shipments, 3 carriers, 2 device vendors. A small, known fraction of
    rows is broken on purpose (bad timestamps, missing fields, out-of-range
    temperatures, duplicate reading ids) so the quality checks have
    something to catch.
    """
    import random

    rng = random.Random(seed)
    carriers = ["NorthStar Freight", "PolarLine Logistics", "ArcticHaul"]
    vendors = ["TempSense", "ColdTrack"]
    products = [("Vaccines", 2.0, 8.0), ("Fresh produce", 0.0, 4.0),
                ("Frozen meals", -25.0, -18.0), ("Biologics", 2.0, 8.0)]
    cities = ["Buffalo, NY", "Chicago, IL", "Dallas, TX", "Atlanta, GA",
              "Seattle, WA", "Newark, NJ"]

    orders: list[dict] = []
    for i in range(240):
        product, lo, hi = products[i % len(products)]
        orders.append({
            "order_ref": f"ORD-{10000 + i}",
            "cust_name": f"Customer {i % 18 + 1:02d}",
            "from_city": cities[i % len(cities)],
            "to_city": cities[(i + 3) % len(cities)],
            "product_name": product,
            "temp_min": lo,
            "temp_max": hi,
            "ship_dt": f"2026-11-{10 + (i % 9):02d}",
            "carrier_name": carriers[i % len(carriers)],
        })

    telemetry_lines: list[str] = []
    rid = 0
    for i, order in enumerate(orders):
        for _ in range(5):  # 5 readings per shipment -> 1,200 readings
            rid += 1
            product, lo, hi = products[i % len(products)]
            if rng.random() < 0.04:  # rare excursion outside the product range
                temp = round(rng.choice(
                    [rng.uniform(lo - 4.0, lo - 0.5),
                     rng.uniform(hi + 0.5, hi + 4.0)]), 1)
            else:
                temp = round(rng.uniform(lo + 0.2, hi - 0.2), 1)
            rec = {
                "id": f"R{rid:05d}",
                "shipment": order["order_ref"],
                "dev": f"{vendors[i % 2]}-{100 + (i % 40)}",
                "ts": f"2026-11-{10 + (i % 9):02d}T{rng.randint(0, 23):02d}:"
                      f"{rng.randint(0, 59):02d}:00Z",
                "tempC": temp,
                "hum": round(rng.uniform(30.0, 70.0), 1),
            }
            if rid % 97 == 0:  # broken timestamp
                rec["ts"] = "not-a-date"
            if rid % 113 == 0:  # missing temperature
                del rec["tempC"]
            if rid % 149 == 0:  # duplicate id of an earlier reading
                rec["id"] = "R00001"
            telemetry_lines.append(json.dumps(rec))

    milestones: list[dict] = []
    events = ["PICKED_UP", "IN_TRANSIT", "IN_TRANSIT", "DELIVERED"]
    for i, order in enumerate(orders):
        for j, event in enumerate(events):
            milestones.append({
                "milestone_id": f"M{i:04d}-{j}",
                "order_ref": order["order_ref"],
                "carrier": order["carrier_name"],
                "status": event,
                "event_time": f"2026-11-{10 + (i % 9):02d} "
                              f"{8 + j * 4:02d}:00:00",
                "loc": cities[(i + j) % len(cities)],
            })

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(milestones[0].keys()))
    writer.writeheader()
    writer.writerows(milestones)

    return {
        "orders": json.dumps(orders, indent=1),
        "telemetry": "\n".join(telemetry_lines),
        "milestones": buf.getvalue(),
    }


def iter_batches(rows: list[dict], size: int = 100) -> Iterable[list[dict]]:
    """Yield rows in batches, the way a queue consumer would."""
    for start in range(0, len(rows), size):
        yield rows[start:start + size]
