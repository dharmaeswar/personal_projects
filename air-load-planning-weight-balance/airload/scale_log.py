"""Digital Scale Log: record platform-scale readings and reconcile them
against the planned load, flagging drift beyond tolerance.

Readings are append-only and auditable: every entry keeps its source
scale, timestamp and weight, and reconciliation reports each mismatch
instead of silently overwriting the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCALE_TOLERANCE_LB = 100.0
SCALE_TOLERANCE_PCT = 1.0


@dataclass(frozen=True)
class ScaleReading:
    scale_id: str
    timestamp: str  # ISO 8601, e.g. "2026-11-24T10:15:00Z"
    item_name: str
    weight_lb: float

    def __post_init__(self) -> None:
        if self.weight_lb < 0:
            raise ValueError(f"scale weight must be >= 0, got {self.weight_lb}")


@dataclass
class ScaleLog:
    readings: list[ScaleReading] = field(default_factory=list)

    def record(self, reading: ScaleReading) -> None:
        self.readings.append(reading)

    def total_for(self, item_name: str) -> float:
        return sum(r.weight_lb for r in self.readings if r.item_name == item_name)

    def reconcile(self, planned: dict[str, float]) -> list[str]:
        """Compare summed scale readings with planned weights per item.

        Returns one plain-language finding per mismatch; an empty list
        means every item reconciles within tolerance.
        """
        findings: list[str] = []
        for item_name, planned_weight in planned.items():
            measured = self.total_for(item_name)
            diff = measured - planned_weight
            tolerance = max(
                SCALE_TOLERANCE_LB, planned_weight * SCALE_TOLERANCE_PCT / 100.0
            )
            if abs(diff) > tolerance:
                findings.append(
                    f"{item_name}: scale total {measured:,.0f} lb vs planned "
                    f"{planned_weight:,.0f} lb (diff {diff:+,.0f} lb, "
                    f"tolerance {tolerance:,.0f} lb)"
                )
        for reading in self.readings:
            if reading.item_name not in planned:
                findings.append(
                    f"{reading.item_name}: scale reading "
                    f"{reading.weight_lb:,.0f} lb has no planned item"
                )
        return findings
