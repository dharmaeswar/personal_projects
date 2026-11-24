"""Auto Load Verification (ALV): independently recompute a load plan and
compare it with the submitted plan, flagging every discrepancy.

The verifier never trusts the plan's own totals: it rebuilds weight, CG
and compartment totals from the raw items and checks them against the
submitted figures within stated tolerances.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .load_plan import LoadPlan
from .weight_balance import AircraftLimits, LoadItem, compute_weight_balance

WEIGHT_TOLERANCE_LB = 50.0
CG_TOLERANCE_MAC = 0.5


@dataclass
class Discrepancy:
    field: str
    submitted: float | str
    recomputed: float | str
    message: str


@dataclass
class VerificationReport:
    flight: str
    passed: bool
    discrepancies: list[Discrepancy] = field(default_factory=list)
    recomputed_weight_lb: float = 0.0
    recomputed_cg_mac: float = 0.0

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"ALV {status} — flight {self.flight}",
            f"recomputed weight {self.recomputed_weight_lb:,.0f} lb, "
            f"CG {self.recomputed_cg_mac:.2f}% MAC",
        ]
        for d in self.discrepancies:
            lines.append(f"  - {d.field}: {d.message}")
        return "\n".join(lines)


def verify_load_plan(
    plan: LoadPlan,
    submitted: dict,
    limits: AircraftLimits | None = None,
) -> VerificationReport:
    """Recompute the plan from its items and compare with `submitted`."""
    limits = limits or AircraftLimits()
    result = compute_weight_balance(plan.items, limits)
    discrepancies: list[Discrepancy] = []

    if abs(submitted.get("total_weight_lb", 0.0) - result.total_weight_lb) > WEIGHT_TOLERANCE_LB:
        discrepancies.append(
            Discrepancy(
                "total_weight_lb",
                submitted.get("total_weight_lb", 0.0),
                result.total_weight_lb,
                f"submitted {submitted.get('total_weight_lb', 0.0):,.0f} lb vs "
                f"recomputed {result.total_weight_lb:,.0f} lb "
                f"(tolerance {WEIGHT_TOLERANCE_LB:.0f} lb)",
            )
        )
    if abs(submitted.get("cg_percent_mac", 0.0) - result.cg_percent_mac) > CG_TOLERANCE_MAC:
        discrepancies.append(
            Discrepancy(
                "cg_percent_mac",
                submitted.get("cg_percent_mac", 0.0),
                result.cg_percent_mac,
                f"submitted {submitted.get('cg_percent_mac', 0.0):.2f}% MAC vs "
                f"recomputed {result.cg_percent_mac:.2f}% MAC "
                f"(tolerance {CG_TOLERANCE_MAC} % MAC)",
            )
        )
    # Rebuild compartment totals from raw items and compare.
    totals: dict[str, float] = {}
    for item in plan.items:
        if item.name.startswith("cargo:"):
            totals[item.name.split(":")[1]] = (
                totals.get(item.name.split(":")[1], 0.0) + item.weight_lb
            )
    for comp, submitted_total in submitted.get("compartments", {}).items():
        if abs(submitted_total - totals.get(comp, 0.0)) > WEIGHT_TOLERANCE_LB:
            discrepancies.append(
                Discrepancy(
                    f"compartment:{comp}",
                    submitted_total,
                    totals.get(comp, 0.0),
                    f"submitted {submitted_total:,.0f} lb vs "
                    f"recomputed {totals.get(comp, 0.0):,.0f} lb",
                )
            )
    for violation in result.violations:
        discrepancies.append(
            Discrepancy("envelope", "within envelope", "violation", violation)
        )
    return VerificationReport(
        flight=plan.flight,
        passed=not discrepancies,
        discrepancies=discrepancies,
        recomputed_weight_lb=result.total_weight_lb,
        recomputed_cg_mac=result.cg_percent_mac,
    )


def verify_items(items: list[LoadItem], limits: AircraftLimits | None = None):
    """Verify a raw item list directly (no submitted figures to compare)."""
    limits = limits or AircraftLimits()
    result = compute_weight_balance(items, limits)
    return result
