"""Load-plan builder: assign cargo to compartments, check limits, emit a plan.

Compartment capacities are stated planning assumptions for the demo
aircraft, not a real load manual. A plan is only valid when every
compartment is within its limit and the weight-and-balance result is
inside the envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .weight_balance import (
    AircraftLimits,
    LoadItem,
    WeightBalanceResult,
    compute_weight_balance,
)

# Stated compartment assumptions: (arm_in, max_weight_lb).
COMPARTMENTS: dict[str, tuple[float, float]] = {
    "FWD": (480.0, 12_000.0),
    "AFT": (640.0, 10_000.0),
    "BULK": (700.0, 4_000.0),
}

FUEL_ARM_IN = 560.0


@dataclass
class LoadPlan:
    flight: str
    items: list[LoadItem] = field(default_factory=list)
    result: WeightBalanceResult | None = None

    def add_cargo(self, uld: str, compartment: str, weight_lb: float) -> None:
        if compartment not in COMPARTMENTS:
            raise ValueError(f"unknown compartment {compartment!r}")
        arm, cap = COMPARTMENTS[compartment]
        used = sum(
            i.weight_lb
            for i in self.items
            if i.name.startswith(f"cargo:{compartment}:")
        )
        if used + weight_lb > cap:
            raise ValueError(
                f"{compartment} hold would hold {used + weight_lb:,.0f} lb, "
                f"over its {cap:,.0f} lb limit"
            )
        self.items.append(LoadItem(f"cargo:{compartment}:{uld}", weight_lb, arm))

    def add_fuel(self, weight_lb: float) -> None:
        self.items.append(LoadItem("fuel:total", weight_lb, FUEL_ARM_IN))

    def finalize(self, limits: AircraftLimits | None = None) -> WeightBalanceResult:
        limits = limits or AircraftLimits()
        self.result = compute_weight_balance(self.items, limits)
        return self.result

    def compartment_totals(self) -> dict[str, float]:
        totals = {c: 0.0 for c in COMPARTMENTS}
        for item in self.items:
            if item.name.startswith("cargo:"):
                totals[item.name.split(":")[1]] += item.weight_lb
        return totals

    def to_dict(self) -> dict:
        if self.result is None:
            raise ValueError("finalize() must run before serializing the plan")
        return {
            "flight": self.flight,
            "items": [
                {"name": i.name, "weight_lb": i.weight_lb, "arm_in": i.arm_in}
                for i in self.items
            ],
            "total_weight_lb": self.result.total_weight_lb,
            "cg_arm_in": round(self.result.cg_arm_in, 2),
            "cg_percent_mac": round(self.result.cg_percent_mac, 2),
            "within_envelope": self.result.within_envelope,
            "violations": self.result.violations,
        }
