"""Zero-curve construction: Nelson-Siegel / Svensson fits and curve bumps.

The curve object exposes continuously compounded zero rates, discount
factors and forward rates.  Fitting is a deterministic grid search over the
decay parameter(s) with a linear least-squares solve for the betas, so the
same market quotes always produce the same curve.
"""

from __future__ import annotations

import numpy as np


def _loadings(tau: np.ndarray, lam: float) -> tuple[np.ndarray, np.ndarray]:
    """Nelson-Siegel factor loadings L1 (level/slope) and L2 (curvature)."""
    tau = np.asarray(tau, dtype=float)
    x = tau / lam
    exp_neg_x = np.exp(-x)
    with np.errstate(divide="ignore", invalid="ignore"):
        l1 = np.where(x == 0.0, 1.0, (1.0 - exp_neg_x) / np.where(x == 0.0, 1.0, x))
    l2 = l1 - exp_neg_x
    return l1, l2


class ZeroCurve:
    """A continuously compounded zero curve defined by a rate function."""

    def __init__(self, rate_fn, label: str = "curve"):
        self._rate_fn = rate_fn
        self.label = label

    def zero_rate(self, tau):
        tau = np.asarray(tau, dtype=float)
        return self._rate_fn(tau)

    def discount(self, tau):
        tau = np.asarray(tau, dtype=float)
        return np.exp(-self.zero_rate(tau) * tau)

    def forward(self, t1: float, t2: float) -> float:
        """Continuously compounded forward rate between t1 and t2 (years)."""
        if t2 <= t1:
            raise ValueError("t2 must be greater than t1")
        z1 = float(self.zero_rate(t1))
        z2 = float(self.zero_rate(t2))
        return (z2 * t2 - z1 * t1) / (t2 - t1)

    def instantaneous_forward(self, t):
        """f(0, t) = d/dt [ t * z(t) ], central difference (forward at 0)."""
        t = np.asarray(t, dtype=float)
        h = 1e-4
        t_plus = t + h
        t_minus = np.maximum(t - h, 0.0)
        span = t_plus - t_minus
        return (t_plus * self.zero_rate(t_plus) - t_minus * self.zero_rate(t_minus)) / span

    def bumped(self, shift: float) -> "ZeroCurve":
        """Parallel-shifted copy of this curve (shift in decimal, e.g. 0.01)."""
        base = self._rate_fn
        return ZeroCurve(lambda tau: base(tau) + shift, label=f"{self.label}{shift:+.4f}")


class NelsonSiegelCurve(ZeroCurve):
    """Nelson-Siegel (and Svensson, when beta3 is set) parametric curve."""

    def __init__(self, beta0, beta1, beta2, lam, beta3=0.0, lam2=None):
        self.beta0, self.beta1, self.beta2 = beta0, beta1, beta2
        self.lam = lam
        self.beta3 = beta3
        self.lam2 = lam2 if lam2 is not None else 2.5

        def rate_fn(tau):
            tau = np.asarray(tau, dtype=float)
            l1, l2 = _loadings(tau, self.lam)
            z = self.beta0 + self.beta1 * l1 + self.beta2 * l2
            if self.beta3:
                _, l2b = _loadings(tau, self.lam2)
                z = z + self.beta3 * l2b
            return z

        super().__init__(rate_fn, label="nelson-siegel")

    def __repr__(self):  # pragma: no cover - cosmetic
        return (
            f"NelsonSiegelCurve(beta0={self.beta0:.4f}, beta1={self.beta1:.4f}, "
            f"beta2={self.beta2:.4f}, lam={self.lam:.2f}, beta3={self.beta3:.4f}, "
            f"lam2={self.lam2:.2f})"
        )


def _design_matrix(maturities, lam, lam2=None):
    l1, l2 = _loadings(maturities, lam)
    cols = [np.ones_like(maturities), l1, l2]
    if lam2 is not None:
        _, l2b = _loadings(maturities, lam2)
        cols.append(l2b)
    return np.column_stack(cols)


def fit_nelson_siegel(maturities, yields, svensson: bool = False) -> tuple[NelsonSiegelCurve, float]:
    """Fit a Nelson-Siegel (or Svensson) curve to zero yields.

    Returns (curve, rmse).  Deterministic: fixed lambda grids, least squares
    for the betas at each grid point, best RMSE wins.
    """
    maturities = np.asarray(maturities, dtype=float)
    yields = np.asarray(yields, dtype=float)
    best = None
    lam_grid = np.arange(0.20, 6.01, 0.05)
    lam2_grid = np.arange(0.30, 8.01, 0.25) if svensson else [None]
    for lam in lam_grid:
        for lam2 in lam2_grid:
            if lam2 is not None and abs(lam2 - lam) < 0.25:
                continue
            X = _design_matrix(maturities, lam, lam2)
            betas, *_ = np.linalg.lstsq(X, yields, rcond=None)
            resid = yields - X @ betas
            rmse = float(np.sqrt(np.mean(resid**2)))
            if best is None or rmse < best[0]:
                best = (rmse, lam, lam2, betas)
    rmse, lam, lam2, betas = best
    beta3 = float(betas[3]) if svensson else 0.0
    curve = NelsonSiegelCurve(
        float(betas[0]), float(betas[1]), float(betas[2]), float(lam),
        beta3=beta3, lam2=float(lam2) if lam2 is not None else 2.5,
    )
    return curve, rmse


def flat_curve(rate: float) -> ZeroCurve:
    """A curve with the same zero rate at every maturity (test/benchmark aid)."""
    return ZeroCurve(lambda tau: np.full_like(np.asarray(tau, dtype=float), rate), label=f"flat{rate:.4f}")
