"""Run the cold-chain telemetry integration pipeline end to end.

Ingest synthetic feeds -> normalise against partner configs -> validate
(quarantine bad rows) -> load into the local warehouse -> print a
monitoring summary with counts, quarantine rate, and excursion alerts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cold_chain.monitor import Warehouse, late_data_alerts, run_summary
from cold_chain.normalize import (load_partner_specs, normalize_milestones,
                                  normalize_orders, normalize_telemetry)
from cold_chain.quality import check_milestones, check_telemetry, excursion_alerts
from cold_chain.sources import (generate_synthetic_feeds,
                                read_carrier_milestones_csv,
                                read_customer_orders_json,
                                read_device_telemetry_jsonl)

BASE = Path(__file__).resolve().parent


def run(seed: int = 42) -> dict:
    started = datetime.now(timezone.utc)
    specs = load_partner_specs(BASE / "configs" / "partners.json")
    feeds = generate_synthetic_feeds(seed)

    raw_orders = read_customer_orders_json(feeds["orders"])
    raw_telemetry = read_device_telemetry_jsonl(feeds["telemetry"])
    raw_milestones = read_carrier_milestones_csv(feeds["milestones"])

    shipments = normalize_orders(raw_orders, specs["customer_orders"])
    by_id = {s.shipment_id: s for s in shipments}

    # Rows that fail normalisation (bad timestamps, missing fields) are
    # quarantined here, before the quality checks see them.
    norm_quarantine: list[dict] = []
    readings = []
    for row in raw_telemetry:
        try:
            readings.extend(normalize_telemetry([row], specs["device_telemetry"]))
        except (KeyError, ValueError, TypeError) as exc:
            norm_quarantine.append({"row": row, "reason": str(exc)})
    milestones = normalize_milestones(raw_milestones, specs["carrier_milestones"])

    tel_report = check_telemetry(readings, by_id)
    mil_report = check_milestones(milestones, by_id)
    alerts = excursion_alerts(readings, by_id)
    late = late_data_alerts(readings, datetime(2026, 11, 19, 12, 0, 0))

    warehouse = Warehouse()
    warehouse.load_shipments(shipments)
    good_readings = [r for r in readings
                     if r.reading_id not in
                     {q["reading_id"] for q in tel_report.quarantined}]
    warehouse.load_readings(good_readings)
    warehouse.load_milestones(milestones)

    finished = datetime.now(timezone.utc)
    summary = run_summary(
        "cold-chain-telemetry-integration", started, finished,
        counts={
            "shipments": len(shipments),
            "telemetry_raw": len(raw_telemetry),
            "telemetry_normalised": len(readings),
            "telemetry_quarantined_at_normalise": len(norm_quarantine),
            "telemetry_loaded": len(warehouse.readings),
            "milestones": len(milestones),
            "milestones_loaded": len(warehouse.milestones),
            "late_readings": len(late),
        },
        reports={"telemetry": tel_report, "milestones": mil_report},
        alerts=alerts,
    )
    summary["warehouse"] = json.loads(warehouse.to_json())
    return summary


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=1, default=str))
