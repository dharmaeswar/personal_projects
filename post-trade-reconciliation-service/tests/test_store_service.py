"""Tests for the SQLite store and the end-to-end service run."""

from run_posttrade import CLEARING, EXECUTIONS, MARKS

from posttrade import store
from posttrade.enrichment import enrich_all
from posttrade.pnl import compute_pnl
from posttrade.positions import build_positions
from posttrade.reconciliation import reconcile
from posttrade.service import run_post_trade


def test_store_round_trip():
    enriched = enrich_all(EXECUTIONS)
    result = reconcile(EXECUTIONS, CLEARING)
    matched = [t for t in enriched if t.execution.exec_id in {m.execution.exec_id for m in result.matches}]
    positions = build_positions(matched)
    pnl_rows = compute_pnl(matched, MARKS)
    conn = store.connect()
    store.save_run(conn, enriched, result, positions, pnl_rows)
    assert len(store.load_positions(conn)) == 4
    assert len(store.load_breaks(conn)) == 4
    assert len(store.load_pnl(conn)) == 4
    aapl_call = next(p for p in store.load_positions(conn) if p["symbol"] == "AAPL 260117C00250000")
    assert aapl_call["net_quantity"] == 6
    assert aapl_call["average_cost"] == 4.20
    conn.close()


def test_service_report_demo_numbers():
    report = run_post_trade(EXECUTIONS, CLEARING, MARKS)
    assert report["executions"] == 8
    assert report["clearing_records"] == 7
    assert report["matched"] == 5
    assert report["breaks"] == 4
    assert report["breaks_by_type"] == {
        "MISSING_CLEARING": 2,
        "MISSING_EXECUTION": 1,
        "QTY_MISMATCH": 1,
    }
    assert report["realised_pnl"] == 120.00
    assert report["unrealised_pnl"] == 590.00
    assert report["total_pnl"] == 710.00
    assert report["stored_positions"] == 4
    assert report["stored_breaks"] == 4


def test_service_excludes_breaks_from_positions():
    report = run_post_trade(EXECUTIONS, CLEARING, MARKS)
    symbols = {p["symbol"] for p in report["positions"]}
    assert "XYZ 260117C00010000" not in symbols  # unknown instrument, unmatched
    assert "SPX 260117P00590000" in symbols  # matched buy stays in the book


def test_service_empty_day():
    report = run_post_trade([], [], {})
    assert report["matched"] == 0
    assert report["breaks"] == 0
    assert report["total_pnl"] == 0.0
    assert report["positions"] == []
