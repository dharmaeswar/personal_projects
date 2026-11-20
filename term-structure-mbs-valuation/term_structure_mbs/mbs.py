"""Agency pass-through MBS cash flows, static and Monte Carlo pricing, OAS.

Cash flows follow the standard level-pay amortisation: each month the pool
pays net-coupon interest on the outstanding balance, scheduled principal
from the mortgage payment, and unscheduled principal from prepayments
(SMM applied to the balance after scheduled principal).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .prepayment import monthly_smm

# Prevailing mortgage rate proxy: 10-year zero rate plus a fixed spread.
MORTGAGE_SPREAD = 0.0170


@dataclass
class Pool:
    balance: float          # current face, currency units
    wac: float              # weighted-average coupon (gross), annual decimal
    net_coupon: float       # pass-through rate to investors, annual decimal
    wam_months: int         # weighted-average maturity, months
    psa: float = 100.0

    def __post_init__(self):
        if self.balance <= 0:
            raise ValueError("balance must be positive")
        if not 0 < self.net_coupon <= self.wac:
            raise ValueError("net coupon must be in (0, WAC]")
        if self.wam_months < 1:
            raise ValueError("WAM must be at least 1 month")


def project_cashflows(pool: Pool, mortgage_rates: np.ndarray) -> dict:
    """Monthly cash flows given a mortgage rate for each month (len >= WAM).

    Returns a dict of arrays (length = months until the balance is repaid,
    at most WAM): investor_interest, scheduled_principal, prepayment,
    total, ending_balance.
    """
    mortgage_rates = np.asarray(mortgage_rates, dtype=float)
    if len(mortgage_rates) < pool.wam_months:
        raise ValueError("mortgage_rates must cover the full WAM")
    i_gross = pool.wac / 12.0
    i_net = pool.net_coupon / 12.0
    bal = float(pool.balance)
    interest, sched, prepay, total, ending = [], [], [], [], []
    for m in range(1, pool.wam_months + 1):
        if bal <= 1e-9:
            break
        n_rem = pool.wam_months - m + 1
        if i_gross > 0:
            pmt = bal * i_gross / (1.0 - (1.0 + i_gross) ** (-n_rem))
        else:
            pmt = bal / n_rem
        int_gross = bal * i_gross
        sp = min(pmt - int_gross, bal)
        smm = monthly_smm(m, pool.wac, float(mortgage_rates[m - 1]), pool.psa)
        pp = smm * (bal - sp)
        inv_int = bal * i_net
        interest.append(inv_int)
        sched.append(sp)
        prepay.append(pp)
        total.append(inv_int + sp + pp)
        bal -= sp + pp
        ending.append(bal)
    return {
        "interest": np.array(interest),
        "scheduled_principal": np.array(sched),
        "prepayment": np.array(prepay),
        "total": np.array(total),
        "ending_balance": np.array(ending),
    }


def _static_mortgage_rate(curve) -> float:
    return float(curve.zero_rate(10.0)) + MORTGAGE_SPREAD


def static_price(pool: Pool, curve, spread: float = 0.0) -> float:
    """Price per 100 of current face, discounting on the curve plus spread."""
    mrate = _static_mortgage_rate(curve)
    cf = project_cashflows(pool, np.full(pool.wam_months, mrate))
    months = np.arange(1, len(cf["total"]) + 1)
    t = months / 12.0
    df = np.exp(-(curve.zero_rate(t) + spread) * t)
    return float(np.sum(cf["total"] * df) / pool.balance * 100.0)


def mc_price(pool: Pool, model, n_paths: int = 200, seed: int = 11, spread: float = 0.0) -> float:
    """Monte Carlo price per 100 under a Hull-White model.

    Each path drives its own prepayments: the prevailing mortgage rate is
    the path's own 10-year zero rate plus MORTGAGE_SPREAD, and cash flows
    are discounted along the path's short rates plus the spread.
    """
    n_months = pool.wam_months
    times = np.arange(0, n_months + 1) / 12.0
    rates = model.simulate(times, n_paths, seed=seed)
    dfs = model.path_discount_factors(times, rates)
    integral = -np.log(dfs)
    prices = np.empty(n_paths)
    for p in range(n_paths):
        # Path 10-year zero rate at each month (window capped at the horizon).
        idx_end = np.minimum(np.arange(n_months) + 120, n_months)
        idx_start = np.arange(n_months)
        window = np.maximum(idx_end - idx_start, 1)
        z10 = (integral[p, idx_end] - integral[p, idx_start]) / (window / 12.0)
        mrates = z10 + MORTGAGE_SPREAD
        cf = project_cashflows(pool, mrates)
        k = len(cf["total"])
        t = np.arange(1, k + 1) / 12.0
        disc = dfs[p, 1 : k + 1] * np.exp(-spread * t)
        prices[p] = np.sum(cf["total"] * disc)
    return float(np.mean(prices) / pool.balance * 100.0)


def solve_oas(pool: Pool, curve, target_price: float, lo: float = -0.02, hi: float = 0.10,
              tol: float = 1e-6, max_iter: int = 200) -> float:
    """Static OAS (decimal) that reprices the pool to target_price (per 100)."""
    p_lo = static_price(pool, curve, lo)
    p_hi = static_price(pool, curve, hi)
    if not (p_hi <= target_price <= p_lo):
        raise ValueError(
            f"target price {target_price:.4f} outside bracket [{p_hi:.4f}, {p_lo:.4f}]"
        )
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        p_mid = static_price(pool, curve, mid)
        if abs(p_mid - target_price) < tol:
            return mid
        if p_mid > target_price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
