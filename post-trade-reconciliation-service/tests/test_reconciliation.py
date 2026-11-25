"""Tests for intraday trade reconciliation."""

import pytest

from posttrade.enrichment import REFERENCE_DATA
from posttrade.models import ClearingRecord, Execution
from posttrade.reconciliation import reconcile


def _exec(exec_id, symbol="AAPL 260117C00250000", side="BUY", qty=10, price=4.20):
    return Execution(exec_id, symbol, side, qty, price, "2026-11-24", "CBOE", "ACC-001")


def _clr(clr_id, symbol="AAPL 260117C00250000", side="BUY", qty=10, price=4.20):
    return ClearingRecord(clr_id, symbol, side, qty, price, "2026-11-24", "ACC-001")


def test_exact_match():
    result = reconcile([_exec("E1")], [_clr("C1")], REFERENCE_DATA)
    assert result.matched_count == 1
    assert result.break_count == 0
    assert result.matches[0].status == "MATCHED"
    assert result.matches[0].price_difference == 0.0


def test_price_within_tolerance_matches_with_variance():
    # Clearing price 4.52 vs execution 4.50: diff 0.02, tolerance 0.05.
    result = reconcile(
        [_exec("E1", side="SELL", qty=4, price=4.50)],
        [_clr("C1", side="SELL", qty=4, price=4.52)],
        REFERENCE_DATA,
    )
    assert result.matched_count == 1
    assert result.matches[0].status == "MATCHED_WITH_PRICE_VARIANCE"
    assert result.matches[0].price_difference == pytest.approx(-0.02)


def test_price_beyond_tolerance_is_price_break():
    result = reconcile(
        [_exec("E1", price=4.20)],
        [_clr("C1", price=4.50)],
        REFERENCE_DATA,
    )
    assert result.matched_count == 0
    assert result.break_count == 1
    assert result.breaks[0].break_type == "PRICE_BREAK"


def test_quantity_mismatch_is_break():
    result = reconcile(
        [_exec("E1", qty=6, price=4.25)],
        [_clr("C1", qty=5, price=4.25)],
        REFERENCE_DATA,
    )
    assert result.matched_count == 0
    assert result.breaks[0].break_type == "QTY_MISMATCH"


def test_missing_clearing_is_break():
    result = reconcile([_exec("E1")], [], REFERENCE_DATA)
    assert result.breaks[0].break_type == "MISSING_CLEARING"
    assert result.breaks[0].execution.exec_id == "E1"
    assert result.breaks[0].clearing is None


def test_missing_execution_is_break():
    result = reconcile([], [_clr("C1")], REFERENCE_DATA)
    assert result.breaks[0].break_type == "MISSING_EXECUTION"
    assert result.breaks[0].clearing.clearing_id == "C1"
    assert result.breaks[0].execution is None


def test_side_mismatch_does_not_match():
    result = reconcile(
        [_exec("E1", side="BUY")],
        [_clr("C1", side="SELL")],
        REFERENCE_DATA,
    )
    assert result.matched_count == 0
    assert {b.break_type for b in result.breaks} == {
        "MISSING_CLEARING",
        "MISSING_EXECUTION",
    }


def test_account_mismatch_does_not_match():
    execs = [_exec("E1")]
    clearing = [ClearingRecord("C1", "AAPL 260117C00250000", "BUY", 10, 4.20, "2026-11-24", "ACC-002")]
    result = reconcile(execs, clearing, REFERENCE_DATA)
    assert result.matched_count == 0
    assert result.break_count == 2


def test_empty_inputs_reconcile_cleanly():
    result = reconcile([], [], REFERENCE_DATA)
    assert result.matched_count == 0
    assert result.break_count == 0
