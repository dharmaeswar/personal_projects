"""Risk-weighted assets and regulatory capital.

Capital = 8% * RWA. RWA = EAD * risk weight, with a standardised-style
weight per asset class (simplified, labelled as such — real standardised
weights depend on counterparty type, rating and maturity):

    rates 20% | fx 20% | equity 100% | credit 100% | commodity 100%

Marginal capital of a trade = capital(book + trade) - capital(book):
the incremental capital a new trade consumes, which is what a trader
needs to price capital-efficiently. Return on capital (RoC) =
expected P&L / marginal capital, the ranking metric for the optimiser.
"""

from __future__ import annotations

from .exposure import ead, trade_addon
from .trades import Trade

CAPITAL_RATIO = 0.08  # Basel minimum total capital ratio

RISK_WEIGHTS = {
    "rates": 0.20,
    "fx": 0.20,
    "equity": 1.00,
    "credit": 1.00,
    "commodity": 1.00,
}


def risk_weight(trade: Trade) -> float:
    return RISK_WEIGHTS[trade.asset_class]


def rwa(trades: list[Trade]) -> float:
    """RWA for a netting set, using per-trade EAD shares.

    EAD is computed for the whole set (netting applies), then split across
    trades in proportion to their standalone add-ons so each trade carries
    a share of the netted EAD. RWA weights then apply per asset class.
    """
    if not trades:
        return 0.0
    total_ead = ead(trades)
    addons = {t.trade_id: trade_addon(t) for t in trades}
    gross_addon = sum(addons.values())
    total = 0.0
    for t in trades:
        share = addons[t.trade_id] / gross_addon if gross_addon > 0 else 1.0 / len(trades)
        total += total_ead * share * risk_weight(t)
    return total


def capital(trades: list[Trade]) -> float:
    """Regulatory capital for a netting set: 8% of RWA."""
    return CAPITAL_RATIO * rwa(trades)


def marginal_capital(book: list[Trade], trade: Trade) -> float:
    """Incremental capital consumed by adding one trade to the book."""
    return capital(book + [trade]) - capital(book)


def return_on_capital(book: list[Trade], trade: Trade) -> float:
    """Expected P&L per dollar of marginal capital; inf if capital is ~0."""
    mc = marginal_capital(book, trade)
    if mc <= 1e-9:
        return float("inf") if trade.expected_pnl > 0 else float("-inf")
    return trade.expected_pnl / mc


def capital_by_desk(trades: list[Trade]) -> dict[str, float]:
    out: dict[str, float] = {}
    for desk in sorted({t.desk for t in trades}):
        out[desk] = capital([t for t in trades if t.desk == desk])
    return out
