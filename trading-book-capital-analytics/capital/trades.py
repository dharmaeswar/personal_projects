"""Synthetic cross-asset trading book.

All trades are synthetic and generated from a fixed seed. No real market
data, no real counterparty names. Asset classes mirror a global markets
trading book: rates, FX, equity, credit and commodities.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Trade:
    trade_id: str
    desk: str            # e.g. "Rates", "FX", "Equities", "Credit", "Commodities"
    asset_class: str     # "rates" | "fx" | "equity" | "credit" | "commodity"
    instrument: str      # "swap" | "forward" | "option" | "cds" | "future"
    notional: float      # USD notional (positive = long / payer)
    mtm: float           # current mark-to-market, USD
    maturity_years: float
    # Supervisory-factor style inputs (simplified SA-CCR add-on parameters)
    supervisory_factor: float
    # Expected annualised P&L of the trade, USD (for return-on-capital ranking)
    expected_pnl: float
    # Collateral held against the trade, USD
    collateral: float = 0.0


def build_book(seed: int = 7) -> list[Trade]:
    """Build a deterministic 30-trade cross-asset book."""
    rng = random.Random(seed)
    specs = [
        # (desk, asset_class, instrument, supervisory_factor, notional range, maturity range)
        ("Rates", "rates", "swap", 0.005, (10e6, 100e6), (1.0, 10.0)),
        ("FX", "fx", "forward", 0.040, (5e6, 50e6), (0.25, 2.0)),
        ("Equities", "equity", "option", 0.320, (1e6, 20e6), (0.25, 2.0)),
        ("Credit", "credit", "cds", 0.050, (5e6, 40e6), (1.0, 5.0)),
        ("Commodities", "commodity", "future", 0.180, (1e6, 15e6), (0.25, 1.0)),
    ]
    trades: list[Trade] = []
    n = 0
    for desk, ac, inst, sf, (lo, hi), (mlo, mhi) in specs:
        for _ in range(6):
            n += 1
            notional = rng.uniform(lo, hi)
            # random direction: half the trades are short / receiver
            sign = 1.0 if rng.random() < 0.5 else -1.0
            mtm = sign * rng.uniform(0.0, 0.02) * notional
            maturity = rng.uniform(mlo, mhi)
            # expected pnl scales with notional and a desk-level spread
            expected_pnl = sign * rng.uniform(0.001, 0.008) * notional
            collateral = max(0.0, mtm) * rng.uniform(0.0, 0.9) if mtm > 0 else 0.0
            trades.append(Trade(
                trade_id=f"T{n:03d}",
                desk=desk,
                asset_class=ac,
                instrument=inst,
                notional=sign * notional,
                mtm=mtm,
                maturity_years=round(maturity, 2),
                supervisory_factor=sf,
                expected_pnl=expected_pnl,
                collateral=round(collateral, 2),
            ))
    return trades


def desks(trades: list[Trade]) -> list[str]:
    seen: list[str] = []
    for t in trades:
        if t.desk not in seen:
            seen.append(t.desk)
    return seen
