"""Energy technical-data layer: synthetic drilling telemetry, data dictionary,
cleaning/validation and EDA.

Mirrors the Landmark (Halliburton) Data Scientist workflow: combine structured
technical data from several sources, clean and validate it before analysis,
maintain a data dictionary so teammates know what each field means and what
its limits are, and explore the data for patterns, anomalies and quality
issues that could affect a model's results.

Everything here is synthetic and seeded: the rate of penetration (ROP) comes
from a simple analytic formula (the ground truth, in the same spirit as the
beam and thermal simulators), with seeded noise and deliberately injected
data-quality problems so the cleaning and validation steps have real work to
do. No real well, rig, or production data is used or claimed.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Data dictionary
# ---------------------------------------------------------------------------
# Each entry documents one field: what it means, its unit, its valid range,
# and where it comes from. The JSON file next to this module is the same
# dictionary in a form a teammate or a software service can read directly.

DATA_DICTIONARY = {
    "well_id": {
        "meaning": "Identifier of the well the reading belongs to.",
        "unit": "identifier",
        "valid_values": "WELL-01 .. WELL-05",
        "source": "drilling operations log",
    },
    "depth_ft": {
        "meaning": "Measured depth of the bit at the time of the reading.",
        "unit": "feet",
        "valid_range": [1000.0, 12000.0],
        "source": "depth sensor",
    },
    "wob_klbf": {
        "meaning": "Weight on bit — downward force applied to the drill bit.",
        "unit": "thousand pounds-force",
        "valid_range": [5.0, 40.0],
        "source": "hook-load sensor",
    },
    "rpm": {
        "meaning": "Rotary speed of the drill string.",
        "unit": "revolutions per minute",
        "valid_range": [40.0, 180.0],
        "source": "top-drive sensor",
    },
    "mud_flow_gpm": {
        "meaning": "Drilling-mud flow rate through the drill string.",
        "unit": "gallons per minute",
        "valid_range": [200.0, 800.0],
        "source": "mud pump sensor",
    },
    "torque_klbf_ft": {
        "meaning": "Rotary torque on the drill string.",
        "unit": "thousand pounds-force feet",
        "valid_range": [2.0, 18.0],
        "source": "top-drive sensor",
    },
    "rop_ft_hr": {
        "meaning": "Rate of penetration — how fast the bit advances through rock.",
        "unit": "feet per hour",
        "valid_range": [1.0, 120.0],
        "source": "derived from depth over time",
    },
}

DICTIONARY_VERSION = "energy-rop-v1"


def load_data_dictionary() -> dict:
    """Load the data dictionary from the JSON file shipped with this module."""
    path = os.path.join(os.path.dirname(__file__), "data_dictionary.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Analytic ground truth: rate of penetration
# ---------------------------------------------------------------------------
# Textbook-style power-law ROP model: penetration rises with weight on bit,
# rotary speed and mud flow, and falls as the well gets deeper (harder rock).
# The formation factor (0.7-1.3 per well) stands in for rock hardness, which
# is not measured directly — the same "known physics, unknown constant"
# pattern as the beam calibration problem.

FORMATION_FACTOR = {
    "WELL-01": 1.15,
    "WELL-02": 0.85,
    "WELL-03": 1.30,
    "WELL-04": 0.70,
    "WELL-05": 1.00,
}


def analytic_rop(wob_klbf: float, rpm: float, mud_flow_gpm: float,
                 depth_ft: float, formation_factor: float = 1.0) -> float:
    """Analytic rate of penetration (ft/hr) for given drilling parameters."""
    if wob_klbf <= 0 or rpm <= 0 or mud_flow_gpm <= 0 or depth_ft <= 0:
        raise ValueError("drilling parameters must be positive")
    rop = (
        18.0
        * (wob_klbf / 20.0) ** 0.6
        * (rpm / 100.0) ** 0.5
        * (mud_flow_gpm / 500.0) ** 0.25
        * math.exp(-depth_ft / 30000.0)
        * formation_factor
    )
    return min(max(rop, 1.0), 120.0)


# ---------------------------------------------------------------------------
# Synthetic data generation (seeded, with injected quality problems)
# ---------------------------------------------------------------------------

def generate_drilling_data(n_rows: int = 400, seed: int = 7) -> pd.DataFrame:
    """Generate synthetic drilling telemetry with injected quality problems.

    About 2% of values are blanked (missing), a few rows carry out-of-range
    sensor values, and a few rows are duplicated — the kind of mess a real
    telemetry feed has, so `clean_and_validate` has something to catch.
    """
    rng = np.random.default_rng(seed)
    wells = list(FORMATION_FACTOR)
    well = rng.choice(wells, size=n_rows)
    depth = rng.uniform(1000.0, 12000.0, size=n_rows)
    wob = rng.uniform(5.0, 40.0, size=n_rows)
    rpm = rng.uniform(40.0, 180.0, size=n_rows)
    flow = rng.uniform(200.0, 800.0, size=n_rows)
    torque = 0.25 * wob + 0.02 * rpm + rng.normal(0.0, 0.8, size=n_rows)
    torque = np.clip(torque, 2.0, 18.0)
    rop = np.array([
        analytic_rop(w, r, f, d, FORMATION_FACTOR[wl])
        for w, r, f, d, wl in zip(wob, rpm, flow, depth, well)
    ])
    rop = rop + rng.normal(0.0, 1.5, size=n_rows)
    rop = np.clip(rop, 1.0, 120.0)

    df = pd.DataFrame({
        "well_id": well,
        "depth_ft": np.round(depth, 1),
        "wob_klbf": np.round(wob, 2),
        "rpm": np.round(rpm, 1),
        "mud_flow_gpm": np.round(flow, 1),
        "torque_klbf_ft": np.round(torque, 2),
        "rop_ft_hr": np.round(rop, 2),
    })

    # Inject quality problems (seeded, so they are reproducible).
    n_missing = max(1, int(0.02 * n_rows))
    missing_rows = rng.choice(n_rows, size=n_missing, replace=False)
    df.loc[missing_rows, "torque_klbf_ft"] = np.nan
    bad_idx = rng.choice(n_rows, size=3, replace=False)
    df.loc[bad_idx[0], "wob_klbf"] = -4.0          # impossible sensor value
    df.loc[bad_idx[1], "rpm"] = 420.0              # out of range
    df.loc[bad_idx[2], "rop_ft_hr"] = 900.0        # impossible ROP
    dup_idx = rng.choice(n_rows, size=4, replace=False)
    df = pd.concat([df, df.loc[dup_idx]], ignore_index=True)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cleaning, validation and EDA
# ---------------------------------------------------------------------------

def _out_of_range(df: pd.DataFrame) -> dict[str, int]:
    """Count values outside the dictionary's valid range, per numeric field."""
    counts: dict[str, int] = {}
    for field, entry in DATA_DICTIONARY.items():
        rng = entry.get("valid_range")
        if rng is None or field not in df.columns:
            continue
        lo, hi = rng
        series = pd.to_numeric(df[field], errors="coerce")
        counts[field] = int(((series < lo) | (series > hi)).sum())
    return counts


def clean_and_validate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Clean a raw telemetry frame and report what was found and fixed.

    Drops rows with missing values, rows outside the dictionary's valid
    ranges, and exact duplicate rows. Returns (cleaned_frame, report).
    The report names every problem found, so a reviewer can tell a data
    problem from a model problem — the distinction the role asks for.
    """
    report: dict = {
        "rows_in": int(len(df)),
        "missing_values": {c: int(df[c].isna().sum()) for c in df.columns
                           if df[c].isna().any()},
        "out_of_range": _out_of_range(df),
        "duplicate_rows": int(df.duplicated().sum()),
    }
    cleaned = df.dropna()
    for field, entry in DATA_DICTIONARY.items():
        rng = entry.get("valid_range")
        if rng is None or field not in cleaned.columns:
            continue
        lo, hi = rng
        series = pd.to_numeric(cleaned[field], errors="coerce")
        cleaned = cleaned[(series >= lo) & (series <= hi)]
    cleaned = cleaned.drop_duplicates()
    report["rows_dropped_missing"] = int(report["rows_in"] - len(df.dropna()))
    report["rows_out"] = int(len(cleaned))
    report["rows_dropped_total"] = int(report["rows_in"] - report["rows_out"])
    return cleaned.reset_index(drop=True), report


def eda_summary(df: pd.DataFrame) -> dict:
    """Exploratory summary: patterns, anomalies and quality issues.

    Returns per-field descriptive stats plus anomaly flags: rows whose ROP
    sits more than 3 standard deviations from the mean, and any field with
    missing values. Flags are reported, never silently dropped.
    """
    numeric = df.select_dtypes(include=[np.number])
    stats = {}
    for col in numeric.columns:
        s = numeric[col]
        stats[col] = {
            "mean": round(float(s.mean()), 3),
            "std": round(float(s.std()), 3),
            "min": round(float(s.min()), 3),
            "max": round(float(s.max()), 3),
            "missing": int(df[col].isna().sum()),
        }
    anomalies: list[dict] = []
    if "rop_ft_hr" in df.columns and len(df) > 1:
        mean = float(df["rop_ft_hr"].mean())
        std = float(df["rop_ft_hr"].std())
        if std > 0:
            flagged = df[(df["rop_ft_hr"] - mean).abs() > 3 * std]
            for idx, row in flagged.iterrows():
                anomalies.append({
                    "row": int(idx),
                    "field": "rop_ft_hr",
                    "value": float(row["rop_ft_hr"]),
                    "z_score": round(float(abs(row["rop_ft_hr"] - mean) / std), 2),
                })
    return {
        "rows": int(len(df)),
        "fields": stats,
        "anomalies_flagged": anomalies,
        "quality_issues": {
            c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()
        },
    }
