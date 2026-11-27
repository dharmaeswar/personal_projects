"""Capital optimisation: spend a capital budget where it earns the most.

1. `allocate(book, candidates, budget)` — greedy fill: rank candidate
   trades by return on marginal capital and take them while the capital
   budget allows. Returns the chosen trades, capital used and expected P&L.
2. `best_hedge(book, hedge_candidates)` — capital-efficient structuring:
   find the hedge trade that cuts book capital the most per dollar of
   expected P&L given up. A hedge with negative expected P&L is a cost;
   the metric is capital saved per dollar of P&L cost.
"""

from __future__ import annotations

from .capital import capital, marginal_capital, return_on_capital
from .trades import Trade


def allocate(book: list[Trade], candidates: list[Trade], budget: float) -> dict:
    """Greedy capital-budget allocation, ranked by return on capital."""
    ranked = sorted(
        candidates,
        key=lambda t: return_on_capital(book, t),
        reverse=True,
    )
    chosen: list[Trade] = []
    used = 0.0
    expected = 0.0
    working = list(book)
    for t in ranked:
        mc = marginal_capital(working, t)
        if mc <= 0:
            # Capital-free (perfectly offsetting) trade: take it only if
            # it does not lose money — a capital saving is not worth a
            # guaranteed P&L loss.
            if t.expected_pnl >= 0:
                chosen.append(t)
                working.append(t)
                expected += t.expected_pnl
            continue
        if used + mc <= budget:
            chosen.append(t)
            working.append(t)
            used += mc
            expected += t.expected_pnl
    return {
        "chosen": chosen,
        "capital_used": used,
        "expected_pnl": expected,
        "capital_left": budget - used,
        "ranking": [(t.trade_id, round(return_on_capital(book, t), 4)) for t in ranked],
    }


def best_hedge(book: list[Trade], hedge_candidates: list[Trade]) -> dict | None:
    """Cheapest capital reduction available from a list of hedge trades.

    Returns the hedge with the highest capital saved per dollar of
    expected P&L given up. Hedges that do not reduce capital, or that
    cost more P&L than the capital they save, are rejected (None).
    """
    base = capital(book)
    best: dict | None = None
    for h in hedge_candidates:
        new_cap = capital(book + [h])
        saved = base - new_cap
        cost = -h.expected_pnl  # P&L given up by putting the hedge on
        if saved <= 0:
            continue
        if cost <= 0:
            # hedge earns P&L and saves capital: strictly dominant
            efficiency = float("inf")
        else:
            efficiency = saved / cost
        if efficiency < 1.0:
            continue
        if best is None or efficiency > best["efficiency"]:
            best = {
                "trade": h,
                "capital_saved": saved,
                "pnl_cost": cost,
                "efficiency": efficiency,
                "new_capital": new_cap,
            }
    return best
