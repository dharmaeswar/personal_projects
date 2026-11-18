"""Exposure profiles from simulated mark-to-market values.

Conventions (see METHODS.md):
  * Discounted exposure at t:  E_t = exp(-r t) * max(V_t, 0)
  * EE(t)  = mean of E_t across paths
  * PFE(t) = configured quantile of E_t across paths
  * EPE    = time-average of EE over the horizon (trapezoidal)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ExposureProfile:
    times: np.ndarray
    ee: np.ndarray
    pfe: np.ndarray
    epe: float


def trapezoid_average(values: np.ndarray, times: np.ndarray) -> float:
    """Time-average of a profile over [times[0], times[-1]]."""
    area = float(np.sum(0.5 * (values[1:] + values[:-1]) * np.diff(times)))
    return area / float(times[-1] - times[0])


def compute_exposure(values: np.ndarray, times: np.ndarray, rate: float,
                     pfe_quantile: float = 0.975) -> ExposureProfile:
    """Build the EE / PFE profile from a (n_paths, n_times) value matrix."""
    values = np.asarray(values, dtype=float)
    times = np.asarray(times, dtype=float)
    discount = np.exp(-rate * times)
    discounted_positive = np.maximum(values, 0.0) * discount
    ee = discounted_positive.mean(axis=0)
    pfe = np.quantile(discounted_positive, pfe_quantile, axis=0)
    return ExposureProfile(times=times, ee=ee, pfe=pfe,
                           epe=trapezoid_average(ee, times))
