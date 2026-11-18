"""Tests for the risk reporting automation toolkit."""

from __future__ import annotations

import csv
import sqlite3

import pytest

from risk_reporting.data import (
    PLANTED_BAD_ROWS,
    PLANTED_BREACH_GROUPS,
    Position,
    generate_all,
    generate_limits,
    generate_positions,
)
from risk_reporting.limits import (
    aggregate_exposures,
    breaches,
    status_for,
    utilisation,
    validate_position,
)
from risk_reporting.pipeline import (
    connect,
    create_tables,
    load_data,
    reconcile,
    sql_limit_results,
)
from risk_reporting.report import render_report, write_outputs
from risk_reporting.stress import (
    LIQUID_ASSETS,
    run_all_scenarios,
    run_scenario,
    total_liquid_assets,
)
from risk_reporting.workflow import (
    ExceptionQueue,
    SignoffChecklist,
    scheduled_run_summary,
)


@pytest.fixture(scope="module")
def data():
    return generate_all()


@pytest.fixture(scope="module")
def limit_results(data):
    results, exceptions = aggregate_exposures(data["positions"], data["limits"])
    return results, exceptions


# --- limit maths ---

def test_utilisation_exact():
    assert utilisation(5_000_000, 10_000_000) == 0.5
    assert utilisation(10_000_000, 10_000_000) == 1.0


def test_utilisation_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        utilisation(100, 0)


def test_status_bands():
    assert status_for(0.899) == "OK"
    assert status_for(0.90) == "WARNING"
    assert status_for(0.999) == "WARNING"
    assert status_for(1.00) == "BREACH"
    assert status_for(1.25) == "BREACH"


def test_validation_rejects_negative_exposure():
    bad = Position("T1", "Rates", "VaR", -1.0, 100.0, "USD")
    assert validate_position(bad) is not None
    good = Position("T2", "Rates", "VaR", 1.0, 100.0, "USD")
    assert validate_position(good) is None


# --- generated data ---

def test_position_and_limit_counts(data):
    # 120 random + 4 planted breach + 2 planted bad rows
    assert len(data["positions"]) == 126
    assert len(data["limits"]) == 20  # 5 desks x 4 risk types
    assert len({p.trade_id for p in data["positions"]}) == 126


def test_generation_is_reproducible():
    assert generate_positions(seed=42) == generate_positions(seed=42)
    assert generate_positions(seed=7) != generate_positions(seed=42)


def test_planted_breach_groups_are_breaches(limit_results):
    results, _ = limit_results
    found = {(r.desk, r.risk_type) for r in breaches(results)}
    assert PLANTED_BREACH_GROUPS <= found
    for r in breaches(results):
        assert r.utilisation >= 1.00


def test_bad_rows_become_exceptions_not_aggregates(limit_results):
    _, exceptions = limit_results
    assert len(exceptions) == len(PLANTED_BAD_ROWS)
    reasons = " ".join(e["reason"] for e in exceptions)
    assert "negative exposure" in reasons
    assert "no limit defined" in reasons
    assert all(e["severity"] == "HIGH" for e in exceptions)


def test_every_limit_group_has_a_result(limit_results):
    results, _ = limit_results
    assert len(results) == 20
    assert all(r.status in {"OK", "WARNING", "BREACH"} for r in results)


# --- SQL pipeline ---

def test_sql_aggregates_match_python(data, limit_results, tmp_path):
    py_results, _ = limit_results
    conn = connect(tmp_path / "test.db")
    try:
        create_tables(conn)
        load_data(conn, data["positions"], data["limits"])
        assert reconcile(py_results, sql_limit_results(conn)) == []
    finally:
        conn.close()


def test_sql_excludes_invalid_rows(data, tmp_path):
    conn = connect(tmp_path / "test.db")
    try:
        create_tables(conn)
        load_data(conn, data["positions"], data["limits"])
        row = conn.execute(
            "SELECT SUM(exposure_usd) FROM positions "
            "WHERE desk = 'Rates' AND risk_type = 'VaR' "
            "AND exposure_usd >= 0"
        ).fetchone()
        sql_total = row[0]
        py_total = next(
            r.exposure_usd for r in sql_limit_results(conn)
            if (r.desk, r.risk_type) == ("Rates", "VaR")
        )
        assert abs(sql_total - py_total) < 0.01
    finally:
        conn.close()


def test_tables_are_populated(data, tmp_path):
    conn = connect(tmp_path / "test.db")
    try:
        create_tables(conn)
        load_data(conn, data["positions"], data["limits"])
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 126
        assert conn.execute("SELECT COUNT(*) FROM limits").fetchone()[0] == 20
    finally:
        conn.close()


# --- liquidity stress ---

def test_liquid_assets_total():
    assert total_liquid_assets() == 78.0
    assert sum(LIQUID_ASSETS.values()) == 78.0


def test_stress_coverage_ratios():
    results = {s.scenario: s for s in run_all_scenarios()}
    assert results["Baseline"].coverage_ratio == pytest.approx(78.0 / 55.0, abs=1e-4)
    assert results["Baseline"].status == "PASS"
    assert results["Adverse"].coverage_ratio == pytest.approx(74.1 / 70.0, abs=1e-4)
    assert results["Adverse"].status == "PASS"
    assert results["Severe"].coverage_ratio == pytest.approx(68.64 / 85.0, abs=1e-4)
    assert results["Severe"].status == "BREACH"


def test_unknown_scenario_rejected():
    with pytest.raises(ValueError):
        run_scenario("Armageddon")


# --- workflow ---

def test_exception_queue_sorts_high_first(limit_results):
    results, exceptions = limit_results
    queue = ExceptionQueue()
    queue.add_breaches(results)
    queue.add_data_exceptions(exceptions)
    ordered = queue.sorted()
    assert len(ordered) == len(breaches(results)) + len(exceptions)
    assert all(e["severity"] == "HIGH" for e in ordered)


def test_signoff_checklist_flow():
    checklist = SignoffChecklist.fresh()
    assert len(checklist.items) == 5
    assert not checklist.all_signed()
    assert len(checklist.pending()) == 5
    checklist.sign("Limit breaches reviewed and explained", "Risk Reporting")
    assert len(checklist.pending()) == 4
    for item in checklist.pending():
        checklist.sign(item, "Risk Reporting")
    assert checklist.all_signed()
    with pytest.raises(ValueError):
        checklist.sign("Not a real item", "Risk Reporting")


def test_scheduled_run_summary_text():
    text = scheduled_run_summary("2026-11-18", 126, 20, 2, 3)
    assert "126 positions" in text
    assert "20 limits checked" in text
    assert "2 breach(es)" in text


# --- report outputs ---

def test_report_text_lists_breaches(limit_results):
    results, exceptions = limit_results
    text = render_report("2026-11-18", results, run_all_scenarios(),
                         exceptions, [])
    assert "BREACH" in text
    assert "Severe" in text
    assert "PASS — no mismatches" in text
    assert "synthetic data" in text


def test_csv_outputs_have_expected_columns(limit_results, tmp_path):
    results, exceptions = limit_results
    paths = write_outputs(tmp_path, results, run_all_scenarios(), exceptions)
    with open(paths["breaches"], newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 20
    assert rows[0]["status"] in {"OK", "WARNING", "BREACH"}
    with open(paths["stress"], newline="") as fh:
        stress_rows = list(csv.DictReader(fh))
    assert [r["scenario"] for r in stress_rows] == [
        "Baseline", "Adverse", "Severe"]
    with open(paths["exceptions"], newline="") as fh:
        exc_rows = list(csv.DictReader(fh))
    assert len(exc_rows) == len(PLANTED_BAD_ROWS)
