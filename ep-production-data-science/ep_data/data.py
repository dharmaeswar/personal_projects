"""Synthetic E&P well production data generator.

All data is synthetic and seeded (fixed RNG seed). It mimics the shape of
monthly well production records an E&P team would hold: one row per well per
month with oil, gas and water volumes, plus completion attributes. No real
well, operator or production data is used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BASINS = ["Permian", "Eagle Ford", "Bakken", "DJ Basin", "Haynesville"]
FLUIDS = ["oil", "gas", "water"]

COLUMN_DESCRIPTIONS = {
    "api_number": "Well identifier, 14-digit API number (synthetic).",
    "basin": "Sedimentary basin the well is drilled in.",
    "completion_date": "Date the well was completed (first production month).",
    "lateral_ft": "Horizontal lateral length in feet.",
    "proppant_lbs": "Total proppant pumped during completion, pounds.",
    "month_index": "Months since first production (0-based).",
    "oil_bbl": "Oil produced in the month, barrels.",
    "gas_mcf": "Gas produced in the month, thousand cubic feet.",
    "water_bbl": "Water produced in the month, barrels.",
    "days_on": "Days the well produced in the month (0-31).",
}


def generate_wells(n_wells: int = 40, seed: int = 42) -> pd.DataFrame:
    """Generate one row per well with static completion attributes."""
    rng = np.random.default_rng(seed)
    api = [f"42{int(rng.integers(100, 999)):03d}{int(rng.integers(10000, 99999)):05d}00"
           for _ in range(n_wells)]
    return pd.DataFrame({
        "api_number": api,
        "basin": rng.choice(BASINS, size=n_wells),
        "completion_date": pd.to_datetime("2022-01-01") + pd.to_timedelta(
            rng.integers(0, 700, size=n_wells), unit="D"),
        "lateral_ft": rng.integers(5000, 11000, size=n_wells).astype(float),
        "proppant_lbs": rng.integers(8_000_000, 25_000_000, size=n_wells).astype(float),
    })


def _arps_rate(qi: float, di: float, b: float, t: np.ndarray) -> np.ndarray:
    """Arps hyperbolic decline: q(t) = qi / (1 + b*di*t)^(1/b)."""
    if b == 0:
        return qi * np.exp(-di * t)
    return qi / (1.0 + b * di * t) ** (1.0 / b)


def generate_monthly_production(wells: pd.DataFrame, n_months: int = 36,
                                seed: int = 42) -> pd.DataFrame:
    """Generate monthly production rows for each well.

    Oil follows an Arps hyperbolic decline from an initial rate that scales
    with lateral length and proppant intensity; gas follows a flatter
    decline; water starts high and falls fast. Noise is multiplicative and
    lognormal, so rates stay positive.
    """
    rng = np.random.default_rng(seed + 1)
    rows = []
    for _, well in wells.iterrows():
        intensity = well["proppant_lbs"] / well["lateral_ft"]  # lbs per ft
        qi_oil = 900.0 * (well["lateral_ft"] / 8000.0) * (intensity / 2000.0) ** 0.5
        qi_oil = float(np.clip(qi_oil, 200.0, 2500.0))
        di = float(rng.uniform(0.06, 0.12))
        b = float(rng.uniform(0.8, 1.4))
        t = np.arange(n_months, dtype=float)
        oil = _arps_rate(qi_oil, di, b, t) * 30.0
        oil *= np.exp(rng.normal(0, 0.08, size=n_months))
        gas = (qi_oil * 1.8 * np.exp(-0.02 * t) * 30.0
               * np.exp(rng.normal(0, 0.08, size=n_months)))
        water = (qi_oil * 2.5 * np.exp(-0.15 * t) * 30.0
                 * np.exp(rng.normal(0, 0.10, size=n_months)))
        days_on = rng.integers(26, 32, size=n_months)
        for m in range(n_months):
            rows.append({
                "api_number": well["api_number"],
                "basin": well["basin"],
                "completion_date": well["completion_date"],
                "lateral_ft": well["lateral_ft"],
                "proppant_lbs": well["proppant_lbs"],
                "month_index": m,
                "oil_bbl": round(float(oil[m]), 1),
                "gas_mcf": round(float(gas[m]), 1),
                "water_bbl": round(float(water[m]), 1),
                "days_on": int(days_on[m]),
            })
    return pd.DataFrame(rows)


def inject_quality_issues(df: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Inject realistic data-quality issues so the cleaning step has work.

    Duplicated rows, a few negative rates, and a few missing values.
    Returns a new frame; the clean generator output is left untouched.
    """
    rng = np.random.default_rng(seed)
    out = df.copy()
    # Duplicates: 8 random rows copied verbatim.
    dup_idx = rng.choice(out.index, size=8, replace=False)
    out = pd.concat([out, out.loc[dup_idx]], ignore_index=True)
    # Negative rates: 5 oil values flipped.
    neg_idx = rng.choice(out.index, size=5, replace=False)
    out.loc[neg_idx, "oil_bbl"] = -out.loc[neg_idx, "oil_bbl"]
    # Missing values: 6 gas values blanked.
    miss_idx = rng.choice(out.index, size=6, replace=False)
    out.loc[miss_idx, "gas_mcf"] = np.nan
    return out


def generate_dataset(n_wells: int = 40, n_months: int = 36, seed: int = 42,
                     with_issues: bool = True) -> pd.DataFrame:
    """Full pipeline: wells -> monthly production -> optional quality issues."""
    wells = generate_wells(n_wells, seed)
    monthly = generate_monthly_production(wells, n_months, seed)
    if with_issues:
        monthly = inject_quality_issues(monthly, seed)
    return monthly
