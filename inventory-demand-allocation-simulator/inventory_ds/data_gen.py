"""Deterministic synthetic data for the inventory-demand simulator.

Generates weekly demand history for a small catalogue of styles across three
regions, plus an on-hand inventory snapshot per fulfillment centre (FC).
Everything is seeded so runs are reproducible. Synthetic data only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STYLES = ["style_A", "style_B", "style_C", "style_D"]
REGIONS = ["west", "central", "east"]
FCS = ["FC_WEST", "FC_CENTRAL", "FC_EAST"]
# Shipping cost per unit from each FC to each region (USD).
SHIP_COST = {
    ("FC_WEST", "west"): 3.0, ("FC_WEST", "central"): 6.0, ("FC_WEST", "east"): 9.0,
    ("FC_CENTRAL", "west"): 6.0, ("FC_CENTRAL", "central"): 3.0, ("FC_CENTRAL", "east"): 6.0,
    ("FC_EAST", "west"): 9.0, ("FC_EAST", "central"): 6.0, ("FC_EAST", "east"): 3.0,
}
# Home FC for each region (nearest-FC sourcing policy).
HOME_FC = {"west": "FC_WEST", "central": "FC_CENTRAL", "east": "FC_EAST"}
STOCKOUT_PENALTY = 25.0  # USD per unmet unit (lost margin + re-ship cost).

BASE_DEMAND = {
    ("style_A", "west"): 120, ("style_A", "central"): 100, ("style_A", "east"): 140,
    ("style_B", "west"): 80, ("style_B", "central"): 90, ("style_B", "east"): 70,
    ("style_C", "west"): 60, ("style_C", "central"): 55, ("style_C", "east"): 75,
    ("style_D", "west"): 40, ("style_D", "central"): 45, ("style_D", "east"): 35,
}
TREND = {"style_A": 1.5, "style_B": 0.8, "style_C": 0.4, "style_D": -0.1}
SEASON_AMP = {"style_A": 25.0, "style_B": 15.0, "style_C": 10.0, "style_D": 8.0}


def generate_demand_history(n_weeks: int = 104, seed: int = 42) -> pd.DataFrame:
    """Weekly demand per style-region with trend, annual seasonality and noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for style in STYLES:
        for region in REGIONS:
            base = BASE_DEMAND[(style, region)]
            for week in range(n_weeks):
                seasonal = SEASON_AMP[style] * np.sin(2 * np.pi * week / 52.0)
                noise = rng.normal(0, 0.08 * base)
                demand = max(0, int(round(base + TREND[style] * week + seasonal + noise)))
                rows.append({"week": week, "style": style, "region": region,
                             "demand": demand})
    return pd.DataFrame(rows)


def generate_inventory(seed: int = 7, n_weeks: int = 104) -> pd.DataFrame:
    """On-hand units per style per FC. Deliberately short of total demand in places.

    Stock is sized to the end-of-history demand level (base + trend over the
    history window), so the allocation problem is tight but solvable: ~92% of
    one week's expected demand, split unevenly across FCs.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for style in STYLES:
        total_demand = sum(BASE_DEMAND[(style, r)] + TREND[style] * (n_weeks - 1)
                           for r in REGIONS)
        # Stock ~92% of one week's total demand, split unevenly across FCs.
        total_stock = int(round(total_demand * 0.92))
        shares = rng.dirichlet([2.0, 2.0, 2.0])
        for fc, share in zip(FCS, shares):
            rows.append({"style": style, "fc": fc,
                         "on_hand": int(round(total_stock * share))})
    return pd.DataFrame(rows)


def generate_ab_experiment(seed: int = 11, n_orders: int = 4000) -> pd.DataFrame:
    """Simulated A/B experiment: control = nearest-FC sourcing, treatment = cost-optimized.

    Each row is one order. fill = 1 if the order shipped complete on time.
    Treatment fills more orders and costs slightly less per order.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for group, p_fill, cost_mean, cost_sd in (
        ("control", 0.90, 7.40, 2.10),
        ("treatment", 0.94, 6.85, 2.05),
    ):
        fills = rng.random(n_orders) < p_fill
        costs = np.clip(rng.normal(cost_mean, cost_sd, n_orders), 1.0, None)
        for i in range(n_orders):
            rows.append({"order_id": f"{group}_{i}", "group": group,
                         "filled": int(fills[i]), "cost": round(float(costs[i]), 2)})
    return pd.DataFrame(rows)
