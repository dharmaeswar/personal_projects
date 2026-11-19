"""Pipeline monitoring, replay, and backfill.

Monitoring: a run summary with per-source counts, quarantine rate, and
alerts (temperature excursions, late data). Replay/backfill: re-run a date
window from the raw feeds; loads are idempotent on reading/milestone id,
so a replay never double-counts.
"""

from __future__ import annotations

import json
from datetime import datetime

from .models import Milestone, Shipment, TelemetryReading
from .quality import QualityReport


def run_summary(name: str, started: datetime, finished: datetime,
                counts: dict[str, int], reports: dict[str, QualityReport],
                alerts: list[dict]) -> dict:
    quarantine_total = sum(len(r.quarantined) for r in reports.values())
    checked_total = sum(r.checked for r in reports.values())
    return {
        "pipeline": name,
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 2),
        "counts": counts,
        "quarantined": quarantine_total,
        "checked": checked_total,
        "quarantine_rate": round(quarantine_total / checked_total, 4)
        if checked_total else 0.0,
        "excursion_alerts": len(alerts),
        "alerts": alerts[:10],
    }


def late_data_alerts(readings: list[TelemetryReading],
                     as_of: datetime, max_age_hours: float = 24.0) -> list[dict]:
    """Readings whose recorded time is far behind the run time."""
    alerts = []
    for reading in readings:
        age_hours = (as_of - reading.recorded_at).total_seconds() / 3600.0
        if age_hours > max_age_hours:
            alerts.append({
                "reading_id": reading.reading_id,
                "shipment_id": reading.shipment_id,
                "age_hours": round(age_hours, 1),
            })
    return alerts


class Warehouse:
    """A tiny local warehouse: JSON files, keyed by id, idempotent loads."""

    def __init__(self) -> None:
        self.shipments: dict[str, Shipment] = {}
        self.readings: dict[str, TelemetryReading] = {}
        self.milestones: dict[str, Milestone] = {}

    def load_shipments(self, items: list[Shipment]) -> int:
        for item in items:
            self.shipments[item.shipment_id] = item
        return len(items)

    def load_readings(self, items: list[TelemetryReading]) -> int:
        added = 0
        for item in items:
            if item.reading_id not in self.readings:
                self.readings[item.reading_id] = item
                added += 1
        return added

    def load_milestones(self, items: list[Milestone]) -> int:
        added = 0
        for item in items:
            if item.milestone_id not in self.milestones:
                self.milestones[item.milestone_id] = item
                added += 1
        return added

    def to_json(self) -> str:
        return json.dumps({
            "shipments": len(self.shipments),
            "readings": len(self.readings),
            "milestones": len(self.milestones),
        }, indent=1)


def replay_window(feeds: dict[str, str], ship_dates: set[str]) -> dict:
    """Backfill helper: filter the raw feeds to one ship-date window.

    Returns the subset of raw rows whose shipment ships in the window, so a
    replay loads exactly that window and nothing else.
    """
    orders = json.loads(feeds["orders"])
    wanted = {o["order_ref"] for o in orders if o["ship_dt"] in ship_dates}
    telemetry = [json.loads(line) for line in feeds["telemetry"].splitlines()
                 if line.strip()]
    return {
        "orders": [o for o in orders if o["ship_dt"] in ship_dates],
        "telemetry": [r for r in telemetry if r["shipment"] in wanted],
        "shipment_ids": sorted(wanted),
    }
