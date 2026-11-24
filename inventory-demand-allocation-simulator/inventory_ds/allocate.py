"""Inventory-to-demand allocation.

Two policies for matching on-hand inventory to forecast demand:
- greedy: serve each region from its home (nearest) FC first, then the cheapest
  remaining FC.
- lp: a linear program (scipy.optimize.linprog) that minimises total shipping cost
  plus a stockout penalty, subject to FC on-hand inventory per style.

Both return an allocation table plus summary metrics (fill rate, unmet units, cost).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from .data_gen import FCS, HOME_FC, REGIONS, SHIP_COST, STOCKOUT_PENALTY


def greedy_allocate(forecast: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Serve each style-region from its home FC first, then cheapest remaining FC."""
    stock = {(r["style"], r["fc"]): int(r["on_hand"]) for _, r in inventory.iterrows()}
    rows = []
    for _, f in forecast.iterrows():
        style, region = f["style"], f["region"]
        remaining = float(f["forecast_week1"])
        order = [HOME_FC[region]] + [fc for fc in FCS if fc != HOME_FC[region]]
        order.sort(key=lambda fc: (fc != HOME_FC[region], SHIP_COST[(fc, region)]))
        for fc in order:
            if remaining <= 0:
                break
            take = min(stock[(style, fc)], remaining)
            if take > 0:
                rows.append({"style": style, "region": region, "fc": fc,
                             "units": float(take), "policy": "greedy",
                             "ship_cost": float(take) * SHIP_COST[(fc, region)]})
                stock[(style, fc)] -= take
                remaining -= take
        if remaining > 0:
            rows.append({"style": style, "region": region, "fc": "UNMET", "units": float(remaining),
                         "policy": "greedy", "ship_cost": float(remaining) * STOCKOUT_PENALTY})
    return pd.DataFrame(rows)


def lp_allocate(forecast: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Minimise shipping cost + stockout penalty with a linear program, per style."""
    rows = []
    for style in sorted(forecast["style"].unique()):
        demand = {r: float(forecast[(forecast["style"] == style)
                                    & (forecast["region"] == r)]["forecast_week1"].iloc[0])
                  for r in REGIONS}
        on_hand = {fc: int(inventory[(inventory["style"] == style)
                                     & (inventory["fc"] == fc)]["on_hand"].iloc[0])
                   for fc in FCS}
        # Variables: x[fc, region] for each pair, plus unmet[region].
        pairs = [(fc, r) for fc in FCS for r in REGIONS]
        n = len(pairs) + len(REGIONS)
        c = np.array([SHIP_COST[p] for p in pairs] + [STOCKOUT_PENALTY] * len(REGIONS))
        # Demand: sum over FCs of x[fc, r] + unmet[r] == demand[r].
        A_eq = np.zeros((len(REGIONS), n))
        b_eq = np.array([demand[r] for r in REGIONS])
        for i, r in enumerate(REGIONS):
            for j, (fc, rr) in enumerate(pairs):
                if rr == r:
                    A_eq[i, j] = 1.0
            A_eq[i, len(pairs) + i] = 1.0
        # Supply: sum over regions of x[fc, r] <= on_hand[fc].
        A_ub = np.zeros((len(FCS), n))
        b_ub = np.array([on_hand[fc] for fc in FCS], dtype=float)
        for i, fc in enumerate(FCS):
            for j, (f2, _) in enumerate(pairs):
                if f2 == fc:
                    A_ub[i, j] = 1.0
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                      bounds=[(0, None)] * n, method="highs")
        if not res.success:
            raise RuntimeError(f"LP failed for {style}: {res.message}")
        for j, (fc, r) in enumerate(pairs):
            if res.x[j] > 1e-6:
                rows.append({"style": style, "region": r, "fc": fc,
                             "units": float(res.x[j]), "policy": "lp",
                             "ship_cost": float(res.x[j]) * SHIP_COST[(fc, r)]})
        for i, r in enumerate(REGIONS):
            if res.x[len(pairs) + i] > 1e-6:
                rows.append({"style": style, "region": r, "fc": "UNMET",
                             "units": float(res.x[len(pairs) + i]), "policy": "lp",
                             "ship_cost": float(res.x[len(pairs) + i]) * STOCKOUT_PENALTY})
    return pd.DataFrame(rows)


def allocation_metrics(allocation: pd.DataFrame, forecast: pd.DataFrame) -> dict:
    """Fill rate, unmet units and cost for one policy's allocation table."""
    total_demand = float(forecast["forecast_week1"].sum())
    filled = float(allocation.loc[allocation["fc"] != "UNMET", "units"].sum())
    unmet = float(allocation.loc[allocation["fc"] == "UNMET", "units"].sum())
    ship = float(allocation.loc[allocation["fc"] != "UNMET", "ship_cost"].sum())
    penalty = float(allocation.loc[allocation["fc"] == "UNMET", "ship_cost"].sum())
    return {
        "policy": allocation["policy"].iloc[0],
        "total_demand": round(total_demand, 1),
        "filled_units": round(filled, 1),
        "unmet_units": round(unmet, 1),
        "fill_rate": round(filled / total_demand, 4) if total_demand else 0.0,
        "shipping_cost": round(ship, 2),
        "stockout_penalty": round(penalty, 2),
        "total_cost": round(ship + penalty, 2),
        "cost_per_filled_unit": round((ship + penalty) / filled, 2) if filled else 0.0,
    }
