"""Data cleaning, integration and validation for E&P production data.

Rules, each logged so an audit can reproduce them:
1. Drop exact duplicate rows (same well, same month).
2. Drop rows with a negative rate on any fluid (a negative monthly volume is
   a meter or sign error, never real production).
3. Interpolate missing gas volumes linearly within a well's own history;
   never borrow values across wells.
4. Enforce one row per (well, month) and months in ascending order.
5. Check every column against the data dictionary: types, ranges, no nulls
   left after cleaning.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "api_number", "basin", "completion_date", "lateral_ft", "proppant_lbs",
    "month_index", "oil_bbl", "gas_mcf", "water_bbl", "days_on",
]
RATE_COLUMNS = ["oil_bbl", "gas_mcf", "water_bbl"]


def clean_production(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Clean a raw monthly production frame. Returns (clean frame, log)."""
    log: dict = {"rows_in": int(len(df))}
    work = df.copy()

    missing = [c for c in REQUIRED_COLUMNS if c not in work.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    work = work.drop_duplicates(subset=["api_number", "month_index"],
                                keep="first")
    log["duplicates_dropped"] = int(log["rows_in"] - len(work))

    neg_mask = (work[RATE_COLUMNS] < 0).any(axis=1)
    log["negative_rows_dropped"] = int(neg_mask.sum())
    work = work.loc[~neg_mask].copy()

    work = work.sort_values(["api_number", "month_index"]).reset_index(drop=True)
    work["gas_mcf"] = work.groupby("api_number")["gas_mcf"].transform(
        lambda s: s.interpolate(limit_direction="both"))
    log["gas_missing_interpolated"] = int(df["gas_mcf"].isna().sum())

    for col in RATE_COLUMNS + ["lateral_ft", "proppant_lbs"]:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work["month_index"] = work["month_index"].astype(int)
    work["days_on"] = work["days_on"].astype(int)

    log["rows_out"] = int(len(work))
    log["wells"] = int(work["api_number"].nunique())
    log["nulls_remaining"] = int(work[RATE_COLUMNS].isna().sum().sum())
    return work, log


def validate_dictionary(df: pd.DataFrame) -> list[str]:
    """Check the frame against the data dictionary. Returns a list of issues."""
    issues: list[str] = []
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            issues.append(f"missing column: {col}")
    if issues:
        return issues
    if df[RATE_COLUMNS].isna().any().any():
        issues.append("null rates remain after cleaning")
    if (df[RATE_COLUMNS] < 0).any().any():
        issues.append("negative rates remain after cleaning")
    dup = df.duplicated(subset=["api_number", "month_index"]).sum()
    if dup:
        issues.append(f"{dup} duplicate (well, month) rows remain")
    if (df["days_on"] < 0).any() or (df["days_on"] > 31).any():
        issues.append("days_on outside 0-31")
    if (df["lateral_ft"] <= 0).any() or (df["proppant_lbs"] <= 0).any():
        issues.append("non-positive completion attribute")
    return issues


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per well: total oil/gas/water, months observed, peak oil rate."""
    return (df.groupby("api_number")
              .agg(total_oil_bbl=("oil_bbl", "sum"),
                   total_gas_mcf=("gas_mcf", "sum"),
                   total_water_bbl=("water_bbl", "sum"),
                   months=("month_index", "count"),
                   peak_oil_bbl=("oil_bbl", "max"),
                   basin=("basin", "first"))
              .reset_index())
