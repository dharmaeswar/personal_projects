"""Validation checks for the capital analytics library.

Each check returns (name, passed, detail) so the runner can print a
plain-language report. Checks are invariants of the model, not fitted
numbers: parity-style identities that must hold for any book.
"""

from __future__ import annotations

import math

from .capital import capital, marginal_capital, return_on_capital, rwa, CAPITAL_RATIO
from .exposure import ALPHA, ead, maturity_factor, netted_addon, replacement_cost, trade_addon
from .optimisation import allocate, best_hedge
from .trades import Trade, build_book


def _check(name, passed, detail=""):
    return (name, bool(passed), detail)


def run_all(book=None) -> list[tuple[str, bool, str]]:
    book = book or build_book()
    checks = []

    # 1. EAD is non-negative and scales with notional.
    small = [Trade("S1", "Rates", "rates", "swap", 10e6, 0.0, 5.0, 0.005, 50_000)]
    big = [Trade("S2", "Rates", "rates", "swap", 20e6, 0.0, 5.0, 0.005, 100_000)]
    checks.append(_check("ead_non_negative", ead(book) >= 0, f"ead={ead(book):,.0f}"))
    checks.append(_check("ead_scales_with_notional", ead(big) > ead(small),
                         f"small={ead(small):,.0f} big={ead(big):,.0f}"))

    # 2. Netting never increases the add-on: offsetting notionals cancel.
    long = Trade("L1", "Rates", "rates", "swap", 50e6, 0.0, 5.0, 0.005, 100_000)
    short = Trade("L2", "Rates", "rates", "swap", -50e6, 0.0, 5.0, 0.005, -100_000)
    gross = trade_addon(long) + trade_addon(short)
    checks.append(_check("netting_reduces_addon",
                         netted_addon([long, short]) < gross,
                         f"netted={netted_addon([long, short]):,.0f} gross={gross:,.0f}"))
    checks.append(_check("perfect_offset_zero_addon",
                         netted_addon([long, short]) == 0.0,
                         f"netted={netted_addon([long, short]):.6f}"))

    # 3. Replacement cost is max(V - C, 0).
    rc = replacement_cost(book)
    v = sum(t.mtm for t in book)
    c = sum(t.collateral for t in book)
    checks.append(_check("replacement_cost_floor",
                         abs(rc - max(v - c, 0.0)) < 1e-6,
                         f"rc={rc:,.0f} v-c={v - c:,.0f}"))

    # 4. Maturity factor is capped at 1 and increasing in maturity.
    checks.append(_check("maturity_factor_capped",
                         maturity_factor(5.0) == 1.0 and maturity_factor(0.25) == 0.5,
                         f"mf(5y)={maturity_factor(5.0)} mf(0.25y)={maturity_factor(0.25)}"))

    # 5. Capital is exactly 8% of RWA.
    checks.append(_check("capital_is_8pct_rwa",
                         abs(capital(book) - CAPITAL_RATIO * rwa(book)) < 1e-6,
                         f"capital={capital(book):,.0f} rwa={rwa(book):,.0f}"))

    # 6. Marginal capital of a trade is non-negative for a same-direction add.
    t = Trade("M1", "Equities", "equity", "option", 10e6, 0.0, 1.0, 0.32, 80_000)
    checks.append(_check("marginal_capital_non_negative",
                         marginal_capital(book, t) >= -1e-6,
                         f"mc={marginal_capital(book, t):,.0f}"))

    # 7. Return on capital is finite and positive for a profitable trade.
    roc = return_on_capital(book, t)
    checks.append(_check("roc_positive_for_profitable_trade",
                         math.isfinite(roc) and roc > 0,
                         f"roc={roc:.4f}"))

    # 8. Optimiser respects the capital budget.
    cands = build_book(seed=99)[:10]
    budget = 2_000_000.0
    result = allocate(book, cands, budget)
    checks.append(_check("optimiser_respects_budget",
                         result["capital_used"] <= budget + 1e-6,
                         f"used={result['capital_used']:,.0f} budget={budget:,.0f} "
                         f"chosen={len(result['chosen'])}"))

    # 9. Optimiser picks higher-RoC trades first (ranking is descending).
    ranking = [r for _, r in result["ranking"]]
    checks.append(_check("optimiser_ranking_descending",
                         ranking == sorted(ranking, reverse=True),
                         f"ranking={ranking[:4]}"))

    # 10. A perfect offset hedge reduces capital (capital-efficient structuring).
    # The hedge is near-costless (small carry cost), so the capital it saves
    # is worth more than the P&L it gives up.
    hedge = Trade("H1", "Rates", "rates", "swap", -50e6, 0.0, 5.0, 0.005, -1_000)
    base_book = [long]
    best = best_hedge(base_book, [hedge])
    checks.append(_check("hedge_reduces_capital",
                         best is not None and best["capital_saved"] > 0,
                         f"saved={best['capital_saved']:,.0f}" if best else "no hedge found"))

    # 11. EAD identity: alpha * (RC + mult * AddOn) with mult in (0, 1].
    addon = netted_addon(book)
    mult = 1.0 if addon <= 0 else min(1.0, 0.05 + 0.95 * math.exp((v - c) / (2.0 * 0.95 * addon)))
    expect = ALPHA * (rc + mult * addon)
    checks.append(_check("ead_identity",
                         abs(ead(book) - expect) < 1e-6,
                         f"ead={ead(book):,.0f} identity={expect:,.0f}"))

    # 12. Book is deterministic: same seed gives the same book.
    again = build_book()
    checks.append(_check("book_deterministic",
                         [t.trade_id for t in again] == [t.trade_id for t in book]
                         and abs(sum(t.notional for t in again) - sum(t.notional for t in book)) < 1e-6,
                         f"trades={len(book)}"))
    return checks


if __name__ == "__main__":
    for name, passed, detail in run_all():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
