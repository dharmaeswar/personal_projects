"""Validation and data-quality checks.

Every normalised record is checked before it loads. A failed check moves
the record to quarantine with a reason — it is never dropped silently and
never blocks the rest of the batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Milestone, Shipment, TelemetryReading

# Physical plausibility bounds for sensor data, independent of product.
ABS_MIN_C, ABS_MAX_C = -40.0, 60.0


@dataclass
class QualityReport:
    checked: int = 0
    passed: int = 0
    quarantined: list[dict] = field(default_factory=list)

    def quarantine_rate(self) -> float:
        return (len(self.quarantined) / self.checked) if self.checked else 0.0


def check_telemetry(readings: list[TelemetryReading],
                    shipments: dict[str, Shipment]) -> QualityReport:
    report = QualityReport(checked=len(readings))
    seen_ids: set[str] = set()
    for reading in readings:
        reasons: list[str] = []
        if reading.reading_id in seen_ids:
            reasons.append("duplicate reading_id")
        seen_ids.add(reading.reading_id)
        shipment = shipments.get(reading.shipment_id)
        if shipment is None:
            reasons.append("unknown shipment_id")
        else:
            if not (ABS_MIN_C <= reading.temperature_c <= ABS_MAX_C):
                reasons.append("temperature outside physical bounds")
            elif not reading.in_range(shipment):
                reasons.append(
                    f"temperature excursion: {reading.temperature_c}C "
                    f"outside {shipment.min_temp_c}..{shipment.max_temp_c}C "
                    f"for {shipment.product}")
        if reasons:
            report.quarantined.append(
                {"reading_id": reading.reading_id, "reasons": reasons})
        else:
            report.passed += 1
    return report


def check_milestones(milestones: list[Milestone],
                     shipments: dict[str, Shipment]) -> QualityReport:
    report = QualityReport(checked=len(milestones))
    seen_ids: set[str] = set()
    allowed = {"PICKED_UP", "IN_TRANSIT", "DELAYED", "OUT_FOR_DELIVERY",
               "DELIVERED", "EXCEPTION"}
    for item in milestones:
        reasons: list[str] = []
        if item.milestone_id in seen_ids:
            reasons.append("duplicate milestone_id")
        seen_ids.add(item.milestone_id)
        if item.shipment_id not in shipments:
            reasons.append("unknown shipment_id")
        if item.event not in allowed:
            reasons.append(f"unknown event {item.event!r}")
        if reasons:
            report.quarantined.append(
                {"milestone_id": item.milestone_id, "reasons": reasons})
        else:
            report.passed += 1
    return report


def excursion_alerts(readings: list[TelemetryReading],
                     shipments: dict[str, Shipment]) -> list[dict]:
    """Temperature excursions that need an alert, one per reading."""
    alerts = []
    for reading in readings:
        shipment = shipments.get(reading.shipment_id)
        if shipment is None:
            continue
        if (ABS_MIN_C <= reading.temperature_c <= ABS_MAX_C
                and not reading.in_range(shipment)):
            alerts.append({
                "reading_id": reading.reading_id,
                "shipment_id": reading.shipment_id,
                "product": shipment.product,
                "temperature_c": reading.temperature_c,
                "allowed_c": [shipment.min_temp_c, shipment.max_temp_c],
                "recorded_at": reading.recorded_at.isoformat(),
            })
    return alerts
