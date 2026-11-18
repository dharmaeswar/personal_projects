"""Portfolio positions and mark-to-market along simulated paths.

Each asset class is treated as its own netting set (see METHODS.md). The
default portfolio holds, per asset class, one long forward and one long
European call, both struck at the spot and maturing at the horizon.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List

import numpy as np

from .pricing import black_scholes_call


@dataclass(frozen=True)
class ForwardPosition:
    asset: str
    strike: float
    maturity: float
    quantity: float  # positive = long

    def mark_to_market(self, spots: np.ndarray, times: np.ndarray,
                       rate: float, volatility: float) -> np.ndarray:
        tau = self.maturity - times
        alive = np.where(tau > 0.0, 1.0, 0.0)
        safe_tau = np.where(tau > 0.0, tau, 0.0)
        return self.quantity * (spots - self.strike * np.exp(-rate * safe_tau)) * alive


@dataclass(frozen=True)
class CallPosition:
    asset: str
    strike: float
    maturity: float
    quantity: float  # positive = long

    def mark_to_market(self, spots: np.ndarray, times: np.ndarray,
                       rate: float, volatility: float) -> np.ndarray:
        tau = self.maturity - times
        unit_price = black_scholes_call(spots, self.strike, np.maximum(tau, 0.0),
                                        rate, volatility)
        return self.quantity * np.asarray(unit_price, dtype=float)


def position_from_dict(data: dict):
    kind = data["type"]
    fields = {k: v for k, v in data.items() if k != "type"}
    if kind == "forward":
        return ForwardPosition(**fields)
    if kind == "call":
        return CallPosition(**fields)
    raise ValueError(f"unknown position type: {kind!r}")


def position_to_dict(position) -> dict:
    data = asdict(position)
    data["type"] = "forward" if isinstance(position, ForwardPosition) else "call"
    return data


# Roughly equal notionals (~100k currency units) across asset classes.
_DEFAULT_QUANTITIES = {"equity_index": 1_000.0, "fx_rate": 100_000.0,
                       "commodity": 1_500.0}


def default_portfolio(assets, horizon_years: float) -> Dict[str, list]:
    """Long forward + long call per asset class, struck at spot."""
    portfolio: Dict[str, list] = {}
    for asset in assets:
        qty = _DEFAULT_QUANTITIES.get(asset.name, round(100_000.0 / asset.spot))
        portfolio[asset.name] = [
            ForwardPosition(asset=asset.name, strike=asset.spot,
                            maturity=horizon_years, quantity=qty),
            CallPosition(asset=asset.name, strike=asset.spot,
                         maturity=horizon_years, quantity=qty),
        ]
    return portfolio


def portfolio_values(positions: List, spots: np.ndarray, times: np.ndarray,
                     rate: float, volatility: float) -> np.ndarray:
    """Net mark-to-market of all positions, shape (n_paths, len(times))."""
    total = np.zeros_like(spots, dtype=float)
    for position in positions:
        total = total + position.mark_to_market(spots, times, rate, volatility)
    return total
