"""Weight-and-balance math for a cargo aircraft load plan.

All numbers are stated planning assumptions for a generic narrow-body
freighter used in this demo, not a real aircraft type certificate.
Weights in pounds, arms in inches from the datum, moments in lb-in.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoadItem:
    """One loadable item: cargo unit, passenger block, or fuel load."""

    name: str
    weight_lb: float
    arm_in: float

    def __post_init__(self) -> None:
        if self.weight_lb < 0:
            raise ValueError(f"weight must be >= 0, got {self.weight_lb}")
        if self.arm_in <= 0:
            raise ValueError(f"arm must be > 0, got {self.arm_in}")

    @property
    def moment(self) -> float:
        return self.weight_lb * self.arm_in


@dataclass
class AircraftLimits:
    """Envelope limits for the demo aircraft (stated assumptions)."""

    empty_weight_lb: float = 90_000.0
    empty_arm_in: float = 550.0
    max_takeoff_weight_lb: float = 170_000.0
    max_zero_fuel_weight_lb: float = 130_000.0
    # Mean aerodynamic chord geometry, used to express CG as % MAC.
    lemac_in: float = 514.0
    mac_in: float = 150.0
    # CG envelope: (weight_lb, forward %MAC, aft %MAC) — linear between points.
    envelope: tuple[tuple[float, float, float], ...] = (
        (100_000.0, 18.0, 28.0),
        (170_000.0, 20.0, 30.0),
    )

    def cg_limits(self, weight_lb: float) -> tuple[float, float]:
        """Forward and aft CG limits (% MAC) at the given weight."""
        (w0, f0, a0), (w1, f1, a1) = self.envelope
        if weight_lb <= w0:
            return f0, a0
        if weight_lb >= w1:
            return f1, a1
        t = (weight_lb - w0) / (w1 - w0)
        return f0 + t * (f1 - f0), a0 + t * (a1 - a0)

    def cg_percent_mac(self, arm_in: float) -> float:
        return (arm_in - self.lemac_in) / self.mac_in * 100.0


@dataclass
class WeightBalanceResult:
    total_weight_lb: float
    cg_arm_in: float
    cg_percent_mac: float
    fwd_limit: float
    aft_limit: float
    within_envelope: bool
    violations: list[str] = field(default_factory=list)


def compute_weight_balance(
    items: list[LoadItem], limits: AircraftLimits
) -> WeightBalanceResult:
    """Compute total weight, CG arm and %MAC, and check every limit."""
    total_weight = limits.empty_weight_lb + sum(i.weight_lb for i in items)
    total_moment = (
        limits.empty_weight_lb * limits.empty_arm_in
        + sum(i.moment for i in items)
    )
    cg_arm = total_moment / total_weight
    cg_mac = limits.cg_percent_mac(cg_arm)
    fwd, aft = limits.cg_limits(total_weight)
    violations: list[str] = []
    if total_weight > limits.max_takeoff_weight_lb:
        violations.append(
            f"takeoff weight {total_weight:,.0f} lb exceeds MTOW "
            f"{limits.max_takeoff_weight_lb:,.0f} lb"
        )
    zero_fuel = total_weight - sum(
        i.weight_lb for i in items if i.name.startswith("fuel:")
    )
    if zero_fuel > limits.max_zero_fuel_weight_lb:
        violations.append(
            f"zero-fuel weight {zero_fuel:,.0f} lb exceeds MZFW "
            f"{limits.max_zero_fuel_weight_lb:,.0f} lb"
        )
    if cg_mac < fwd:
        violations.append(
            f"CG {cg_mac:.2f}% MAC is forward of the {fwd:.1f}% MAC limit"
        )
    if cg_mac > aft:
        violations.append(
            f"CG {cg_mac:.2f}% MAC is aft of the {aft:.1f}% MAC limit"
        )
    return WeightBalanceResult(
        total_weight_lb=total_weight,
        cg_arm_in=cg_arm,
        cg_percent_mac=cg_mac,
        fwd_limit=fwd,
        aft_limit=aft,
        within_envelope=not violations,
        violations=violations,
    )
