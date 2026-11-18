"""XVA calculations: CVA, FVA and KVA from an exposure profile.

Formulas (EE is already discounted; see METHODS.md for the full write-up):
  * Survival under a flat hazard rate h:  S(t) = exp(-h t)
  * Bucket default probability:           dPD_i = S(t_{i-1}) - S(t_i)
  * CVA = LGD * sum_i EE(t_i) * dPD_i
  * FVA = funding_spread * sum_i EE(t_i) * dt_i          (funding cost proxy)
  * Capital proxy K(t) = capital_fraction * PFE(t)
  * KVA = cost_of_capital * sum_i K(t_i) * dt_i
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from .config import XVAConfig
from .exposure import ExposureProfile


def default_probability_increments(times: np.ndarray, hazard_rate: float) -> np.ndarray:
    """Marginal default probabilities per bucket, aligned to times[1:]."""
    survival = np.exp(-hazard_rate * np.asarray(times, dtype=float))
    return survival[:-1] - survival[1:]


def cva_contributions(profile: ExposureProfile, cfg: XVAConfig) -> np.ndarray:
    """Per-bucket CVA contributions, aligned to profile.times (first = 0)."""
    dpd = default_probability_increments(profile.times, cfg.hazard_rate)
    contrib = cfg.lgd * profile.ee[1:] * dpd
    return np.concatenate([[0.0], contrib])


def fva_contributions(profile: ExposureProfile, cfg: XVAConfig) -> np.ndarray:
    dt = np.diff(profile.times)
    contrib = cfg.funding_spread * profile.ee[1:] * dt
    return np.concatenate([[0.0], contrib])


def kva_contributions(profile: ExposureProfile, cfg: XVAConfig) -> np.ndarray:
    dt = np.diff(profile.times)
    capital = cfg.capital_fraction * profile.pfe[1:]
    contrib = cfg.cost_of_capital * capital * dt
    return np.concatenate([[0.0], contrib])


def xva_totals(profile: ExposureProfile, cfg: XVAConfig) -> Dict[str, float]:
    return {
        "cva": float(cva_contributions(profile, cfg).sum()),
        "fva": float(fva_contributions(profile, cfg).sum()),
        "kva": float(kva_contributions(profile, cfg).sum()),
    }


def xva_ladder(profile: ExposureProfile, cfg: XVAConfig,
               horizons=(1.0, 2.0, 3.0, 4.0, 5.0)) -> List[Dict[str, float]]:
    """Cumulative XVA ladder: XVA accrued up to each horizon year."""
    cum_cva = np.cumsum(cva_contributions(profile, cfg))
    cum_fva = np.cumsum(fva_contributions(profile, cfg))
    cum_kva = np.cumsum(kva_contributions(profile, cfg))
    rows: List[Dict[str, float]] = []
    for horizon in horizons:
        idx = int(np.argmin(np.abs(profile.times - horizon)))
        rows.append({
            "horizon_years": float(profile.times[idx]),
            "ee": float(profile.ee[idx]),
            "pfe": float(profile.pfe[idx]),
            "cum_cva": float(cum_cva[idx]),
            "cum_fva": float(cum_fva[idx]),
            "cum_kva": float(cum_kva[idx]),
            "cum_total_xva": float(cum_cva[idx] + cum_fva[idx] + cum_kva[idx]),
        })
    return rows
