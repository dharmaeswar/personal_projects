"""LP / MILP optimization layer for inventory-demand allocation.

Formulates allocation as a linear program (continuous relaxation) and as a
mixed-integer program (integer units) solved with ``scipy.optimize.milp``
(HiGHS). Also provides scenario and sensitivity analysis over shipping
costs, stockout penalties, demand levels and lead-time penalties, in the
spirit of operations-research validation: benchmark comparison against the
greedy and LP policies in ``allocate.py``, plus sensitivity / scenario
checks on the inputs that drive the optimum.

Demo project, synthetic data only. No solver other than SciPy is used and
no supply-chain employment experience is claimed by this module.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from .allocate import allocation_metrics
from .data_gen import FCS, REGIONS, SHIP_COST, STOCKOUT_PENALTY

# Lead time in days from each FC to each region (mirrors the cost pattern:
# home FC is fastest, the far FC is slowest).
LEAD_TIME_DAYS = {
    ("FC_WEST", "west"): 1, ("FC_WEST", "central"): 3, ("FC_WEST", "east"): 5,
    ("FC_CENTRAL", "west"): 3, ("FC_CENTRAL", "central"): 1, ("FC_CENTRAL", "east"): 3,
    ("FC_EAST", "west"): 5, ("FC_EAST", "central"): 3, ("FC_EAST", "east"): 1,
}


def _solve_one_style(demand, on_hand, *, integer, ship_cost_multiplier,
                       stockout_penalty, lead_time_penalty_per_day):
    pairs = [(fc, r) for fc in FCS for r in REGIONS]
    n_ship = len(pairs)
    n = n_ship + len(REGIONS)
    c = np.array(
        [SHIP_COST[p] * ship_cost_multiplier
         + lead_time_penalty_per_day * LEAD_TIME_DAYS[p] for p in pairs]
        + [float(stockout_penalty)] * len(REGIONS), dtype=float)
    # Demand equality: sum_fc x[fc, r] + unmet[r] == demand[r]
    A_eq = np.zeros((len(REGIONS), n))
    for i, r in enumerate(REGIONS):
        for j, (_, rr) in enumerate(pairs):
            if rr == r:
                A_eq[i, j] = 1.0
        A_eq[i, n_ship + i] = 1.0
    b_eq = np.array([demand[r] for r in REGIONS], dtype=float)
    # Supply: sum_r x[fc, r] <= on_hand[fc]
    A_ub = np.zeros((len(FCS), n))
    for i, fc in enumerate(FCS):
        for j, (f2, _) in enumerate(pairs):
            if f2 == fc:
                A_ub[i, j] = 1.0
    b_ub = np.array([on_hand[fc] for fc in FCS], dtype=float)
    constraints = [
        LinearConstraint(A_eq, lb=b_eq, ub=b_eq),
        LinearConstraint(A_ub, lb=-np.inf, ub=b_ub),
    ]
    # Shipped units are integer; unmet stays continuous so fractional
    # forecast demand remains feasible (the fraction lands in unmet).
    integrality = np.zeros(n)
    if integer:
        integrality[:n_ship] = 1.0
    res = milp(c, integrality=integrality, bounds=Bounds(0, np.inf),
               constraints=constraints)
    if not res.success:
        raise RuntimeError(f"MILP/LP solve failed: {res.message}")
    return pairs, res.x


def optimize_allocation(forecast: pd.DataFrame, inventory: pd.DataFrame, *,
                        integer: bool = True, ship_cost_multiplier: float = 1.0,
                        stockout_penalty: float = STOCKOUT_PENALTY,
                        demand_multiplier: float = 1.0,
                        lead_time_penalty_per_day: float = 0.0) -> pd.DataFrame:
    """Solve allocation as MILP (integer units) or LP (integer=False).

    Objective: minimise shipping cost (scaled by ``ship_cost_multiplier``)
    plus a lead-time penalty per shipped unit plus the stockout penalty on
    unmet demand, subject to per-FC on-hand supply and per-region demand.
    """
    policy = "milp" if integer else "lp_opt"
    rows = []
    for style in sorted(forecast["style"].unique()):
        sub = forecast[forecast["style"] == style]
        demand = {r: float(sub[sub["region"] == r]["forecast_week1"].iloc[0]) * demand_multiplier
                  for r in REGIONS}
        on_hand = {fc: int(inventory[(inventory["style"] == style)
                                     & (inventory["fc"] == fc)]["on_hand"].iloc[0])
                   for fc in FCS}
        pairs, x = _solve_one_style(
            demand, on_hand, integer=integer,
            ship_cost_multiplier=ship_cost_multiplier,
            stockout_penalty=stockout_penalty,
            lead_time_penalty_per_day=lead_time_penalty_per_day)
        for j, (fc, r) in enumerate(pairs):
            if x[j] > 1e-6:
                units = float(round(x[j])) if integer else float(x[j])
                rows.append({"style": style, "region": r, "fc": fc, "units": units,
                             "policy": policy,
                             "ship_cost": units * SHIP_COST[(fc, r)] * ship_cost_multiplier})
        for i, r in enumerate(REGIONS):
            v = x[len(pairs) + i]
            if v > 1e-6:
                units = float(v)
                rows.append({"style": style, "region": r, "fc": "UNMET", "units": units,
                             "policy": policy, "ship_cost": units * float(stockout_penalty)})
    return pd.DataFrame(rows)


def milp_allocate(forecast, inventory, **kwargs):
    """Integer-unit allocation via MILP."""
    return optimize_allocation(forecast, inventory, integer=True, **kwargs)


def lp_relaxation_allocate(forecast, inventory, **kwargs):
    """Continuous LP relaxation of the same formulation."""
    return optimize_allocation(forecast, inventory, integer=False, **kwargs)


def scenario_analysis(forecast: pd.DataFrame, inventory: pd.DataFrame,
                      scenarios: list[dict] | None = None) -> pd.DataFrame:
    """Run named scenarios varying costs, penalties, demand and lead time.

    Each scenario is a dict with a ``name`` plus any keyword accepted by
    :func:`optimize_allocation`. Returns one metrics row per scenario.
    """
    if scenarios is None:
        scenarios = [
            {"name": "base"},
            {"name": "ship_cost_+20pct", "ship_cost_multiplier": 1.2},
            {"name": "ship_cost_-20pct", "ship_cost_multiplier": 0.8},
            {"name": "demand_+10pct", "demand_multiplier": 1.1},
            {"name": "stockout_penalty_x2", "stockout_penalty": STOCKOUT_PENALTY * 2},
            {"name": "lead_time_penalty", "lead_time_penalty_per_day": 0.5},
        ]
    rows = []
    for sc in scenarios:
        kwargs = {k: v for k, v in sc.items() if k != "name"}
        alloc = milp_allocate(forecast, inventory, **kwargs)
        # Metrics are scored against the (possibly scaled) demand actually solved.
        fc_eval = forecast.copy()
        fc_eval["forecast_week1"] = fc_eval["forecast_week1"] * kwargs.get("demand_multiplier", 1.0)
        m = allocation_metrics(alloc, fc_eval)
        m["scenario"] = sc["name"]
        rows.append(m)
    cols = ["scenario"] + [c for c in rows[0] if c != "scenario"]
    return pd.DataFrame(rows)[cols]


def sensitivity_analysis(forecast: pd.DataFrame, inventory: pd.DataFrame,
                         cost_multipliers=(0.8, 1.0, 1.2),
                         stockout_penalties=None) -> pd.DataFrame:
    """One-at-a-time sensitivity of total cost / fill rate to key inputs."""
    if stockout_penalties is None:
        stockout_penalties = (STOCKOUT_PENALTY * 0.5, STOCKOUT_PENALTY, STOCKOUT_PENALTY * 2)
    rows = []
    for mult in cost_multipliers:
        m = allocation_metrics(milp_allocate(forecast, inventory, ship_cost_multiplier=mult), forecast)
        rows.append({"parameter": "ship_cost_multiplier", "value": float(mult),
                     "total_cost": m["total_cost"], "fill_rate": m["fill_rate"],
                     "unmet_units": m["unmet_units"]})
    for pen in stockout_penalties:
        m = allocation_metrics(milp_allocate(forecast, inventory, stockout_penalty=float(pen)), forecast)
        rows.append({"parameter": "stockout_penalty", "value": float(pen),
                     "total_cost": m["total_cost"], "fill_rate": m["fill_rate"],
                     "unmet_units": m["unmet_units"]})
    return pd.DataFrame(rows)
