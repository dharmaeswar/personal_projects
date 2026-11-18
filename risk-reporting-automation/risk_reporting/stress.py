"""Simple liquidity-stress scenarios.

Coverage ratio = liquid assets (after haircut) / stressed outflows.
A ratio below 1.00 means stressed outflows exceed liquid assets: a
liquidity breach. Figures are synthetic, in $ billions.
"""

from __future__ import annotations

from dataclasses import dataclass

# Liquid-asset buckets ($bn). Total = 78.0.
LIQUID_ASSETS = {
    "Cash": 22.0,
    "Government securities": 38.0,
    "High-quality corporate bonds": 12.0,
    "Other liquid assets": 6.0,
}

# Outflow base ($bn) before the scenario run-off rate is applied.
OUTFLOW_BASE = 100.0

SCENARIOS = {
    # name: (run-off rate on outflows, haircut on liquid assets)
    "Baseline": (0.55, 0.00),
    "Adverse": (0.70, 0.05),
    "Severe": (0.85, 0.12),
}


@dataclass(frozen=True)
class StressResult:
    scenario: str
    liquid_assets: float
    stressed_outflows: float
    coverage_ratio: float
    status: str  # PASS | BREACH


def total_liquid_assets(assets: dict[str, float] | None = None) -> float:
    return round(sum((assets or LIQUID_ASSETS).values()), 2)


def run_scenario(
    scenario: str,
    assets: dict[str, float] | None = None,
    outflow_base: float = OUTFLOW_BASE,
) -> StressResult:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    if outflow_base < 0:
        raise ValueError("outflow base must not be negative")
    run_off, haircut = SCENARIOS[scenario]
    liquid = round(total_liquid_assets(assets) * (1 - haircut), 2)
    outflows = round(outflow_base * run_off, 2)
    ratio = round(liquid / outflows, 4) if outflows else float("inf")
    return StressResult(
        scenario=scenario,
        liquid_assets=liquid,
        stressed_outflows=outflows,
        coverage_ratio=ratio,
        status="PASS" if ratio >= 1.00 else "BREACH",
    )


def run_all_scenarios(
    assets: dict[str, float] | None = None,
    outflow_base: float = OUTFLOW_BASE,
) -> list[StressResult]:
    return [run_scenario(name, assets, outflow_base) for name in SCENARIOS]
