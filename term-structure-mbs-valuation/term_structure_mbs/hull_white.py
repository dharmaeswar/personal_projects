"""Hull-White one-factor short-rate model fitted to an initial zero curve.

dr(t) = (theta(t) - a * r(t)) dt + sigma dW(t), with theta chosen so the
model reproduces the input curve exactly.  Simulation uses the standard
decomposition r(t) = x(t) + alpha(t), dx = -a x dt + sigma dW, x(0) = 0,
which is exact for the OU component and needs no theta discretisation.
"""

from __future__ import annotations

import numpy as np


class HullWhiteModel:
    def __init__(self, curve, a: float, sigma: float):
        if a < 0:
            raise ValueError("mean reversion a must be non-negative")
        if sigma < 0:
            raise ValueError("volatility sigma must be non-negative")
        self.curve = curve
        self.a = float(a)
        self.sigma = float(sigma)

    # -- curve fitting ----------------------------------------------------
    def alpha(self, t):
        """alpha(t) = f(0,t) + sigma^2/(2 a^2) * (1 - exp(-a t))^2."""
        t = np.asarray(t, dtype=float)
        f = self.curve.instantaneous_forward(t)
        if self.a == 0.0:
            adj = 0.5 * self.sigma**2 * t**2
        else:
            adj = (self.sigma**2 / (2.0 * self.a**2)) * (1.0 - np.exp(-self.a * t)) ** 2
        return f + adj

    def short_rate_at_zero(self) -> float:
        return float(self.alpha(0.0))

    # -- analytic bond pricing --------------------------------------------
    def _B(self, t: float, T: float) -> float:
        if self.a == 0.0:
            return T - t
        return (1.0 - np.exp(-self.a * (T - t))) / self.a

    def bond_price(self, t: float, T: float, r_t: float) -> float:
        """P(t, T) for a zero-coupon bond given the short rate r_t at time t."""
        if T < t:
            raise ValueError("T must be >= t")
        B = self._B(t, T)
        p_t = float(self.curve.discount(t)) if t > 0 else 1.0
        p_T = float(self.curve.discount(T))
        f_t = float(self.curve.instantaneous_forward(t))
        if self.a == 0.0:
            lnA = np.log(p_T / p_t) + B * f_t - 0.5 * self.sigma**2 * t * B**2
        else:
            lnA = (
                np.log(p_T / p_t)
                + B * f_t
                - (self.sigma**2 / (4.0 * self.a)) * (1.0 - np.exp(-2.0 * self.a * t)) * B**2
            )
        return float(np.exp(lnA - B * r_t))

    # -- simulation ---------------------------------------------------------
    def simulate(self, times, n_paths: int, seed: int = 7) -> np.ndarray:
        """Short-rate paths on the given time grid. Shape (n_paths, len(times)).

        times must start at 0 and be increasing (years).
        """
        times = np.asarray(times, dtype=float)
        if times[0] != 0.0 or np.any(np.diff(times) <= 0):
            raise ValueError("times must start at 0 and be strictly increasing")
        rng = np.random.default_rng(seed)
        x = np.zeros(n_paths)
        paths = np.empty((n_paths, len(times)))
        paths[:, 0] = self.alpha(times[0])
        for k in range(1, len(times)):
            dt = times[k] - times[k - 1]
            if self.a == 0.0:
                decay = 1.0
                vol = self.sigma * np.sqrt(dt)
            else:
                decay = np.exp(-self.a * dt)
                vol = self.sigma * np.sqrt((1.0 - np.exp(-2.0 * self.a * dt)) / (2.0 * self.a))
            x = x * decay + vol * rng.standard_normal(n_paths)
            paths[:, k] = x + self.alpha(times[k])
        return paths

    @staticmethod
    def path_discount_factors(times, rates: np.ndarray) -> np.ndarray:
        """Discount factor to each grid time along each path (trapezoid rule).

        rates has shape (n_paths, len(times)); returns the same shape, with
        DF(0) = 1 in the first column.
        """
        times = np.asarray(times, dtype=float)
        dt = np.diff(times)
        increments = 0.5 * (rates[:, 1:] + rates[:, :-1]) * dt
        integral = np.concatenate(
            [np.zeros((rates.shape[0], 1)), np.cumsum(increments, axis=1)], axis=1
        )
        return np.exp(-integral)
