"""Independent benchmarks: Monte Carlo output vs closed-form references.

Two independent checks, each reported against the tolerance band:
  1. Option price -- Black-Scholes price of the call at t=0 vs the simulated
     discounted mean payoff (antithetic variates, large path count).
  2. Forward EE  -- analytic expected exposure of the long forward at a
     mid-horizon time bucket vs the simulated EE at the same bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .config import AssetClass
from .pricing import analytic_forward_expected_exposure, black_scholes_call
from .simulation import simulate_terminal

BENCHMARK_PATHS = 200_000


@dataclass
class BenchmarkCheck:
    name: str
    asset: str
    simulated: float
    reference: float
    relative_error: float
    tolerance: float
    passed: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "asset": self.asset,
            "simulated": self.simulated,
            "reference": self.reference,
            "relative_error": self.relative_error,
            "tolerance": self.tolerance,
            "passed": self.passed,
        }


def _make_check(name: str, asset: str, simulated: float, reference: float,
                tolerance: float) -> BenchmarkCheck:
    rel_error = abs(simulated - reference) / abs(reference) if reference != 0 else abs(simulated)
    return BenchmarkCheck(name=name, asset=asset, simulated=float(simulated),
                          reference=float(reference),
                          relative_error=float(rel_error),
                          tolerance=float(tolerance),
                          passed=bool(rel_error <= tolerance))


def check_option_price(asset: AssetClass, strike: float, maturity: float,
                       rate: float, tolerance: float,
                       n_paths: int = BENCHMARK_PATHS, seed: int = 12345) -> BenchmarkCheck:
    """Per-unit call price: Monte Carlo discounted payoff vs Black-Scholes."""
    rng = np.random.default_rng(seed)
    terminal = simulate_terminal(asset.spot, asset.volatility, rate, maturity,
                                 n_paths, rng, antithetic=True)
    payoff = np.maximum(terminal - strike, 0.0)
    simulated = float(np.exp(-rate * maturity) * payoff.mean())
    reference = float(black_scholes_call(asset.spot, strike, maturity, rate,
                                         asset.volatility))
    return _make_check("option_price_black_scholes", asset.name, simulated,
                       reference, tolerance)


def check_forward_ee(asset: AssetClass, strike: float, maturity: float,
                     t_star: float, rate: float, tolerance: float,
                     n_paths: int = BENCHMARK_PATHS, seed: int = 6789) -> BenchmarkCheck:
    """Per-unit discounted EE of the long forward at t_star vs analytic EE."""
    rng = np.random.default_rng(seed)
    spots = simulate_terminal(asset.spot, asset.volatility, rate, t_star,
                              n_paths, rng, antithetic=True)
    values = spots - strike * np.exp(-rate * (maturity - t_star))
    simulated = float(np.exp(-rate * t_star) * np.maximum(values, 0.0).mean())
    reference = analytic_forward_expected_exposure(asset.spot, strike, maturity,
                                                   t_star, rate, asset.volatility)
    return _make_check("forward_ee_analytic", asset.name, simulated, reference,
                       tolerance)


def run_benchmarks(assets, portfolio, sim_cfg, xva_cfg) -> List[BenchmarkCheck]:
    """Run both independent checks for every asset class."""
    checks: List[BenchmarkCheck] = []
    t_star = 0.5 * sim_cfg.horizon_years
    for i, asset in enumerate(assets):
        positions = portfolio[asset.name]
        call = next(p for p in positions if p.__class__.__name__ == "CallPosition")
        fwd = next(p for p in positions if p.__class__.__name__ == "ForwardPosition")
        checks.append(check_option_price(
            asset, call.strike, call.maturity, sim_cfg.risk_free_rate,
            xva_cfg.tolerance, seed=10_000 + i))
        checks.append(check_forward_ee(
            asset, fwd.strike, fwd.maturity, t_star, sim_cfg.risk_free_rate,
            xva_cfg.tolerance, seed=20_000 + i))
    return checks
