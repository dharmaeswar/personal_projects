"""Exposure at default (EAD) under a simplified SA-CCR-style method.

EAD = alpha * (Replacement Cost + Potential Future Exposure)
  alpha = 1.4 (Basel SA-CCR)
  Replacement Cost = max(V - C, 0) where V is net mark-to-market and C
  collateral, floored at zero for a single netting set.
  Potential Future Exposure = multiplier * AddOn, where
  AddOn = sum over trades of |notional| * supervisory_factor * maturity_factor
  and maturity_factor = sqrt(min(M, 1yr) / 1yr) (capped at 1), and
  multiplier = min(1, 0.05 + 0.95 * exp((V - C) / (2 * 0.95 * AddOn))).

Netting benefit: within one netting set, long and short notionals in the same
asset class partially offset. The offset factor is the absolute net notional
divided by the gross notional for that asset class; AddOn uses the netted
notional. This is a deliberately simplified teaching model, not a regulatory
calculation — the simplification is labelled everywhere it matters.
"""

from __future__ import annotations

import math

from .trades import Trade

ALPHA = 1.4


def maturity_factor(maturity_years: float) -> float:
    """sqrt(min(M, 1) / 1): longer trades carry more future exposure, capped at 1y."""
    return math.sqrt(min(max(maturity_years, 0.0), 1.0) / 1.0)


def trade_addon(trade: Trade) -> float:
    """Standalone add-on for one trade (no netting)."""
    return abs(trade.notional) * trade.supervisory_factor * maturity_factor(trade.maturity_years)


def netted_addon(trades: list[Trade]) -> float:
    """Add-on with same-asset-class netting: offsetting notionals cancel."""
    by_class: dict[str, list[Trade]] = {}
    for t in trades:
        by_class.setdefault(t.asset_class, []).append(t)
    total = 0.0
    for ac, group in by_class.items():
        gross = sum(abs(t.notional) for t in group)
        net = abs(sum(t.notional for t in group))
        offset = net / gross if gross > 0 else 0.0
        # add-on per trade scaled by the class offset factor
        total += sum(trade_addon(t) for t in group) * offset
    return total


def replacement_cost(trades: list[Trade]) -> float:
    """max(V - C, 0) for the netting set."""
    v = sum(t.mtm for t in trades)
    c = sum(t.collateral for t in trades)
    return max(v - c, 0.0)


def multiplier(trades: list[Trade], addon: float) -> float:
    """PFE multiplier: over-collateralised sets get a smaller multiplier."""
    if addon <= 0:
        return 1.0
    v = sum(t.mtm for t in trades)
    c = sum(t.collateral for t in trades)
    return min(1.0, 0.05 + 0.95 * math.exp((v - c) / (2.0 * 0.95 * addon)))


def ead(trades: list[Trade], netting: bool = True) -> float:
    """Exposure at default for a netting set of trades."""
    addon = netted_addon(trades) if netting else sum(trade_addon(t) for t in trades)
    rc = replacement_cost(trades)
    return ALPHA * (rc + multiplier(trades, addon) * addon)


def ead_by_desk(trades: list[Trade]) -> dict[str, float]:
    """EAD per desk (each desk treated as its own netting set)."""
    out: dict[str, float] = {}
    for desk in sorted({t.desk for t in trades}):
        out[desk] = ead([t for t in trades if t.desk == desk])
    return out
