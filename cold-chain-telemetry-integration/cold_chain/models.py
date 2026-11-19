"""Shared shipment and telemetry models.

Every source (device vendor, carrier, customer system) is mapped into these
two models. Field names, units, and timestamp formats are normalised here so
downstream checks only ever see one shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Shipment:
    """One customer order moving through the cold chain."""

    shipment_id: str
    order_id: str
    customer: str
    origin: str
    destination: str
    product: str
    min_temp_c: float
    max_temp_c: float
    ship_date: str  # YYYY-MM-DD
    carrier: str

    def temp_range(self) -> tuple[float, float]:
        return (self.min_temp_c, self.max_temp_c)


@dataclass(frozen=True)
class TelemetryReading:
    """One normalised device reading for a shipment."""

    reading_id: str
    shipment_id: str
    device_id: str
    recorded_at: datetime
    temperature_c: float
    humidity_pct: float | None = None
    source: str = "device"
    raw: dict = field(default_factory=dict, compare=False)

    def in_range(self, shipment: Shipment) -> bool:
        lo, hi = shipment.temp_range()
        return lo <= self.temperature_c <= hi


@dataclass(frozen=True)
class Milestone:
    """One normalised carrier milestone for a shipment."""

    milestone_id: str
    shipment_id: str
    carrier: str
    event: str  # PICKED_UP, IN_TRANSIT, DELAYED, DELIVERED, ...
    event_at: datetime
    location: str
    source: str = "carrier"
    raw: dict = field(default_factory=dict, compare=False)


def parse_ts(value: str) -> datetime:
    """Parse the timestamp formats our partners send.

    Accepts ISO 8601 with 'Z' or an offset, and 'YYYY-MM-DD HH:MM:SS'.
    Raises ValueError on anything else so bad timestamps quarantine.
    """
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    raise ValueError(f"unparseable timestamp: {value!r}")
