"""Tests for single-pass batch computation with snapshot-keyed caching."""

import time

import pytest
from decimal import Decimal

from perf.batch import FundData, compute_batch
from perf.decimal_solver import solve_irr_decimal
from perf.pme import ks_pme

D = Decimal


def _fund(fund_id, contribution="100", distribution="121",
          terminal_nav="0"):
    return FundData(
        fund_id=fund_id,
        flows=((D(0), D(contribution)), (D(1), D("-" + distribution))),
        index_levels=((D(0), D(100)), (D(1), D(110))),
        end_day=D(1),
        terminal_nav=D(terminal_nav),
        start_value=D(100),
        end_value=D(110),
    )


DEFINITIONS = ["irr_decimal", "modified_dietz_decimal", "ks_pme",
               "direct_alpha", "long_nickels_pme"]


def test_batch_values_match_direct_calls():
    fund = _fund("F1")
    out = compute_batch([fund], DEFINITIONS)
    results = out["results"]["F1"]
    assert results["irr_decimal"] == solve_irr_decimal(
        [(D(0), D(-100)), (D(1), D(121))])[0]
    assert results["ks_pme"] == ks_pme(
        fund.flows, dict(fund.index_levels))
    assert results["ks_pme"] == D("1.1")
    assert results["long_nickels_pme"] == D("1.1")
    assert out["stats"]["funds"] == 1
    assert out["stats"]["computations"] == 5
    assert out["stats"]["cache_hits"] == 0


def test_batch_long_nickels_counts_terminal_nav():
    # FV(C) = 100 * 110/100 = 110; FV(D) = 121 * 110/110 = 121;
    # (121 + 11) / 110 = 1.2.
    fund = _fund("F2", terminal_nav="11")
    out = compute_batch([fund], ["long_nickels_pme"])
    assert out["results"]["F2"]["long_nickels_pme"] == D("1.2")


def test_batch_cache_reuses_identical_snapshots():
    fund_a = _fund("A")
    fund_b = _fund("B")  # same inputs, different id
    cache = {}
    first = compute_batch([fund_a], DEFINITIONS, cache=cache)
    assert first["stats"]["computations"] == 5
    second = compute_batch([fund_a, fund_b], DEFINITIONS, cache=cache)
    assert second["stats"]["computations"] == 0
    assert second["stats"]["cache_hits"] == 10
    assert second["results"]["A"] == second["results"]["B"]


def test_batch_changed_snapshot_recomputes():
    cache = {}
    compute_batch([_fund("A")], DEFINITIONS, cache=cache)
    changed = _fund("A", distribution="122")
    out = compute_batch([changed], DEFINITIONS, cache=cache)
    assert out["stats"]["computations"] == 5
    assert out["stats"]["cache_hits"] == 0
    assert out["results"]["A"]["ks_pme"] != D("1.1")


def test_batch_rejects_unknown_definition():
    with pytest.raises(ValueError, match="unknown measure"):
        compute_batch([_fund("A")], ["not_a_measure"])


def test_batch_scale_smoke():
    # 300 synthetic funds x 5 definitions in one pass; the design
    # target is ~15,000 funds x ~150 definitions, so this smoke test
    # checks the pass scales linearly, not the full volume.
    funds = [_fund("F%03d" % i, contribution=str(100 + i),
                   distribution=str(110 + i)) for i in range(300)]
    start = time.monotonic()
    out = compute_batch(funds, DEFINITIONS)
    elapsed = time.monotonic() - start
    assert len(out["results"]) == 300
    assert out["stats"]["computations"] == 1500
    assert elapsed < 30
