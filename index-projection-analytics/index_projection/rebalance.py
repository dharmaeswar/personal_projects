"""Projected index rebalances.

Rank the current constituents plus eligible candidates by free-float
market capitalisation, take the top N as the projected index, and report
additions, deletions, projected weights and one-way turnover (half the
sum of absolute weight changes, the standard turnover definition).
"""

from dataclasses import dataclass, field

from .universe import Constituent, IndexUniverse


@dataclass
class RebalanceProjection:
    projected_tickers: list
    additions: list
    deletions: list
    projected_weights: dict
    turnover: float  # one-way turnover as a fraction, 0..1


def project_rebalance(
    universe: IndexUniverse,
    candidates: list,
    target_count: int,
) -> RebalanceProjection:
    """Project the next rebalance: top `target_count` names by market cap."""
    ranked = sorted(
        list(universe.constituents.values()) + list(candidates),
        key=lambda c: c.free_float_mcap,
        reverse=True,
    )
    projected = ranked[:target_count]
    projected_tickers = [c.ticker for c in projected]
    current = set(universe.constituents)
    additions = [t for t in projected_tickers if t not in current]
    deletions = [t for t in current if t not in projected_tickers]
    total = sum(c.free_float_mcap for c in projected)
    projected_weights = {c.ticker: c.free_float_mcap / total for c in projected}
    old_weights = universe.weights()
    union = set(old_weights) | set(projected_weights)
    turnover = (
        sum(abs(projected_weights.get(t, 0.0) - old_weights.get(t, 0.0)) for t in union)
        / 2.0
    )
    return RebalanceProjection(
        projected_tickers=projected_tickers,
        additions=additions,
        deletions=deletions,
        projected_weights=projected_weights,
        turnover=turnover,
    )
