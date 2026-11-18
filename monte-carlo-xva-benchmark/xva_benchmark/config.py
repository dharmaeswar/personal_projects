"""Configuration objects for the Monte-Carlo XVA Benchmark Framework.

All configuration is expressed with plain dataclasses so that payloads can be
pickled and shipped to worker processes unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List


@dataclass(frozen=True)
class AssetClass:
    """A simulated underlier: one GBM asset class."""

    name: str
    spot: float
    volatility: float


@dataclass(frozen=True)
class SimulationConfig:
    n_paths: int = 10_000
    n_steps: int = 50
    horizon_years: float = 5.0
    seed: int = 42
    risk_free_rate: float = 0.03
    parallel: bool = True


@dataclass(frozen=True)
class XVAConfig:
    hazard_rate: float = 0.02          # flat counterparty hazard rate (per year)
    lgd: float = 0.60                  # loss given default
    funding_spread: float = 0.015      # funding spread over risk-free (per year)
    capital_fraction: float = 0.10     # capital proxy = fraction of PFE
    cost_of_capital: float = 0.10      # cost of capital rate (per year)
    pfe_quantile: float = 0.975        # PFE confidence level
    tolerance: float = 0.012           # benchmark tolerance band (1.2%)


def default_asset_classes() -> List[AssetClass]:
    """Three asset classes with distinct spots and volatilities."""
    return [
        AssetClass(name="equity_index", spot=100.0, volatility=0.20),
        AssetClass(name="fx_rate", spot=1.10, volatility=0.08),
        AssetClass(name="commodity", spot=75.0, volatility=0.30),
    ]


def config_to_dict(sim: SimulationConfig, xva: XVAConfig,
                   assets: List[AssetClass]) -> dict:
    return {
        "simulation": asdict(sim),
        "xva": asdict(xva),
        "asset_classes": [asdict(a) for a in assets],
    }
