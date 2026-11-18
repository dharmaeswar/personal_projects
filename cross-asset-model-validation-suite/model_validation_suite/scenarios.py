"""Scenario loading and grid expansion.

Reads the YAML config and expands each asset class's base inputs over its
shock grid (Cartesian product), producing one scenario dict per grid point.
Each scenario carries a fully-resolved ``context`` dict for the invariant
functions, so re-running the same config always produces the same coverage.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import yaml

from .models.rates import DiscountCurve

DEFAULT_TOLERANCES = {"parity": 1e-9, "short_end": 1e-3}


def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    if not isinstance(config, dict):
        raise ValueError(f"config {path} did not parse to a mapping")
    return config


def _tolerances(config: dict) -> dict:
    tol = dict(DEFAULT_TOLERANCES)
    tol.update(config.get("tolerances", {}) or {})
    return {k: float(v) for k, v in tol.items()}


def expand_scenarios(config: dict) -> list[dict]:
    """Expand the config into a flat list of scenario dicts."""
    tolerances = _tolerances(config)
    scenarios: list[dict] = []

    # ---- Interest rates: parallel curve shifts ---------------------------
    if "rates" in config:
        block = config["rates"]
        base, shocks = block["base"], block.get("shocks", {})
        for shift_bp in shocks.get("parallel_shift_bp", [0]):
            shifted = [r + shift_bp / 10_000.0 for r in base["zero_rates"]]
            vasicek = dict(base["vasicek"])
            vasicek["r0"] = vasicek["r0"] + shift_bp / 10_000.0
            scenarios.append({
                "id": f"rates/shift{shift_bp:+d}bp",
                "asset_class": "rates",
                "context": {
                    "curve": DiscountCurve(base["maturities"], shifted),
                    "par_yields": list(base["par_yields"]),
                    "par_maturities": list(base["par_maturities"]),
                    "vasicek": vasicek,
                    "tolerances": tolerances,
                },
            })

    # ---- FX: spot x vol shock grid ---------------------------------------
    if "fx" in config:
        block = config["fx"]
        base, shocks = block["base"], block.get("shocks", {})
        for spot_pct, vol_pts in itertools.product(
                shocks.get("spot_pct", [0]), shocks.get("vol_points", [0.0])):
            scenarios.append({
                "id": f"fx/spot{spot_pct:+d}pct_vol{vol_pts:+.2f}",
                "asset_class": "fx",
                "context": {
                    "spot": base["spot"] * (1.0 + spot_pct / 100.0),
                    "domestic_rate": float(base["domestic_rate"]),
                    "foreign_rate": float(base["foreign_rate"]),
                    "vol": max(base["vol"] + vol_pts, 0.01),
                    "tenor": float(base["tenor"]),
                    "strikes": [float(k) for k in base["strikes"]],
                    "tolerances": tolerances,
                },
            })

    # ---- Equity: spot x vol shock grid ------------------------------------
    if "equity" in config:
        block = config["equity"]
        base, shocks = block["base"], block.get("shocks", {})
        for spot_pct, vol_pts in itertools.product(
                shocks.get("spot_pct", [0]), shocks.get("vol_points", [0.0])):
            scenarios.append({
                "id": f"equity/spot{spot_pct:+d}pct_vol{vol_pts:+.2f}",
                "asset_class": "equity",
                "context": {
                    "spot": base["spot"] * (1.0 + spot_pct / 100.0),
                    "rate": float(base["rate"]),
                    "vol": max(base["vol"] + vol_pts, 0.01),
                    "tenor": float(base["tenor"]),
                    "strikes": [float(k) for k in base["strikes"]],
                    "tolerances": tolerances,
                },
            })

    return scenarios
