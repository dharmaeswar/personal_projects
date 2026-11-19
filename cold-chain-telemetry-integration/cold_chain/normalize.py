"""Mapping and normalisation.

Partner specs live in configs/partners.json: one entry per partner, with the
field mapping from the partner's names to the shared model, the timestamp
format, and the temperature unit. Adding a partner means adding a config
entry, not new code — the configuration-driven pipeline the JD asks for.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Milestone, Shipment, TelemetryReading, parse_ts


def load_partner_specs(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _map(row: dict, mapping: dict[str, str]) -> dict:
    """Rename partner fields to shared-model fields; missing keys stay out."""
    return {target: row[source] for source, target in mapping.items()
            if source in row}


def normalize_orders(rows: list[dict], spec: dict) -> list[Shipment]:
    out: list[Shipment] = []
    for row in rows:
        m = _map(row, spec["field_map"])
        # The order feed has one id: the order ref is the shipment id.
        out.append(Shipment(
            shipment_id=m["order_id"],
            order_id=m["order_id"],
            customer=m["customer"],
            origin=m["origin"],
            destination=m["destination"],
            product=m["product"],
            min_temp_c=float(m["min_temp_c"]),
            max_temp_c=float(m["max_temp_c"]),
            ship_date=str(m["ship_date"]),
            carrier=m["carrier"],
        ))
    return out


def normalize_telemetry(rows: list[dict], spec: dict) -> list[TelemetryReading]:
    out: list[TelemetryReading] = []
    for row in rows:
        m = _map(row, spec["field_map"])
        temp = float(m["temperature_c"])
        if spec.get("temp_unit") == "F":  # partner sends Fahrenheit
            temp = round((temp - 32.0) * 5.0 / 9.0, 1)
        out.append(TelemetryReading(
            reading_id=str(m["reading_id"]),
            shipment_id=str(m["shipment_id"]),
            device_id=str(m["device_id"]),
            recorded_at=parse_ts(str(m["recorded_at"])),
            temperature_c=temp,
            humidity_pct=(float(m["humidity_pct"])
                          if m.get("humidity_pct") is not None else None),
            source=spec.get("name", "device"),
            raw=row,
        ))
    return out


def normalize_milestones(rows: list[dict], spec: dict) -> list[Milestone]:
    out: list[Milestone] = []
    for row in rows:
        m = _map(row, spec["field_map"])
        out.append(Milestone(
            milestone_id=str(m["milestone_id"]),
            shipment_id=str(m["shipment_id"]),
            carrier=str(m["carrier"]),
            event=str(m["event"]).upper(),
            event_at=parse_ts(str(m["event_at"])),
            location=str(m["location"]),
            source=spec.get("name", "carrier"),
            raw=row,
        ))
    return out
