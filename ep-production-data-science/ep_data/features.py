"""Feature engineering for E&P production data.

Features are computed per well, in time order, using only information
available up to that month (no look-ahead):
- cumulative oil / gas / water
- water cut (water / total fluids) and gas-oil ratio (GOR)
- 3-month rolling average oil rate
- month-on-month decline rate
- proppant intensity (lbs per lateral foot) — a completion feature
- months on production (same as month_index, kept explicit for modelling)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "cum_oil_bbl", "cum_gas_mcf", "cum_water_bbl", "water_cut", "gor_mcf_bbl",
    "oil_3m_avg", "decline_rate", "proppant_intensity", "months_on_prod",
    "lateral_ft", "oil_bbl_lag1",
]


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered features. Input must be cleaned and sorted."""
    work = df.sort_values(["api_number", "month_index"]).copy()
    g = work.groupby("api_number")

    work["cum_oil_bbl"] = g["oil_bbl"].cumsum()
    work["cum_gas_mcf"] = g["gas_mcf"].cumsum()
    work["cum_water_bbl"] = g["water_bbl"].cumsum()

    total_fluids = work["oil_bbl"] + work["water_bbl"]
    work["water_cut"] = np.where(total_fluids > 0,
                                 work["water_bbl"] / total_fluids, 0.0)
    work["gor_mcf_bbl"] = np.where(work["oil_bbl"] > 0,
                                   work["gas_mcf"] / work["oil_bbl"], 0.0)

    work["oil_3m_avg"] = g["oil_bbl"].transform(
        lambda s: s.rolling(3, min_periods=1).mean())
    work["oil_bbl_lag1"] = g["oil_bbl"].shift(1)
    prev = work["oil_bbl_lag1"]
    work["decline_rate"] = np.where(prev.notna() & (prev > 0),
                                    (prev - work["oil_bbl"]) / prev, 0.0)

    work["proppant_intensity"] = work["proppant_lbs"] / work["lateral_ft"]
    work["months_on_prod"] = work["month_index"]

    # First month has no lag; fill with its own rate so the row stays usable.
    work["oil_bbl_lag1"] = work["oil_bbl_lag1"].fillna(work["oil_bbl"])
    return work
