"""Tests for the trading-book capital analytics library."""

import math

import pytest

from capital.capital import (
    CAPITAL_RATIO,
    capital,
    marginal_capital,
    return_on_capital,
    rwa,
)
from capital.exposure import (
    ead,
    maturity_factor,
    multiplier,
    netted_addon,
    replacement_cost,
    trade_addon,
)
from capital.optimisation import allocate, best_hedge
from capital.trades import Trade, build_book
from capital.validation import run_all


def _trade(tid="T1", notional=10e6, mtm=0.0, maturity=5.0, sf=0.005,
           pnl=50_000, ac="rates", desk="Rates", inst="swap"):
    return Trade(tid, desk, ac, inst, notional, mtm, maturity, sf, pnl)


def test_ead_non_negative_and_scales_with_notional():
    small = [_trade(notional=10e6)]
    big = [_trade(notional=20e6)]
    assert ead(small) >= 0
    assert ead(big) > ead(small)


def test_perfect_offset_gives_zero_addon():
    long = _trade("L1", notional=50e6)
    short = _trade("L2", notional=-50e6)
    assert netted_addon([long, short]) == 0.0
    assert netted_addon([long, short]) < trade_addon(long) + trade_addon(short)


def test_partial_netting_reduces_addon():
    a = _trade("A1", notional=50e6)
    b = _trade("A2", notional=-20e6)
    assert netted_addon([a, b]) < trade_addon(a) + trade_addon(b)
    assert netted_addon([a, b]) > 0


def test_replacement_cost_floored_at_zero():
    underwater = [_trade(mtm=-100_000)]
    assert replacement_cost(underwater) == 0.0
    in_money = [_trade(mtm=100_000)]
    assert replacement_cost(in_money) == 100_000


def test_maturity_factor_capped_and_monotone():
    assert maturity_factor(5.0) == 1.0
    assert maturity_factor(0.25) == 0.5
    assert maturity_factor(0.25) < maturity_factor(1.0)


def test_multiplier_bounded():
    book = build_book()
    m = multiplier(book, netted_addon(book))
    assert 0.05 < m <= 1.0


def test_capital_is_eight_percent_of_rwa():
    book = build_book()
    assert abs(capital(book) - CAPITAL_RATIO * rwa(book)) < 1e-6
    assert capital([]) == 0.0
    assert rwa([]) == 0.0


def test_marginal_capital_and_roc():
    book = build_book()
    t = _trade("M1", notional=10e6, ac="equity", desk="Equities",
               inst="option", sf=0.32, pnl=80_000)
    assert marginal_capital(book, t) >= 0
    roc = return_on_capital(book, t)
    assert math.isfinite(roc) and roc > 0


def test_optimiser_respects_budget_and_ranks_by_roc():
    book = build_book()
    cands = build_book(seed=99)[:10]
    budget = 2_000_000.0
    result = allocate(book, cands, budget)
    assert result["capital_used"] <= budget + 1e-6
    assert result["capital_left"] >= -1e-6
    rocs = [r for _, r in result["ranking"]]
    assert rocs == sorted(rocs, reverse=True)
    assert len(result["chosen"]) >= 1


def test_hedge_reduces_capital():
    base = [_trade("L1", notional=50e6)]
    # near-costless offset: small carry cost, large capital saving
    hedge = _trade("H1", notional=-50e6, pnl=-1_000)
    best = best_hedge(base, [hedge])
    assert best is not None
    assert best["capital_saved"] > 0
    assert best["new_capital"] < capital(base)


def test_hedge_rejected_when_it_does_not_save_capital():
    base = build_book()
    # a tiny same-direction trade adds capital instead of saving it
    no_hedge = _trade("N1", notional=1e6, pnl=-100)
    assert best_hedge(base, [no_hedge]) is None


def test_book_deterministic():
    a = build_book()
    b = build_book()
    assert len(a) == 30
    assert [t.trade_id for t in a] == [t.trade_id for t in b]
    assert sum(t.notional for t in a) == sum(t.notional for t in b)
    assert len({t.desk for t in a}) == 5


def test_all_validation_checks_pass():
    failed = [(n, d) for n, ok, d in run_all() if not ok]
    assert failed == [], failed
