"""Tests for the DAG pipeline: order, full run, resume, retry."""

from datetime import date
from pathlib import Path

from homehealth import pipeline, warehouse

BASE = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 26)


def run_demo(conn, run_id="demo-test"):
    return pipeline.run(
        conn,
        str(BASE / "data" / "visits.csv"),
        str(BASE / "data" / "referrals.json"),
        run_id=run_id,
        today=TODAY,
        incremental=False,
    )


def test_task_order_respects_dependencies():
    order = pipeline.task_order()
    assert order == ["ingest", "validate", "load", "reconcile", "publish"]


def test_full_run_report():
    conn = warehouse.connect()
    report = run_demo(conn)
    assert report["source_rows"] == 16
    assert report["referrals"] == 6
    assert report["api_retries"] == 1
    assert report["loaded"] == 12
    assert report["quarantined"] == 4
    assert report["fact_rows"] == 12
    assert report["reconciled"] is True
    assert report["tasks"] == {t: "done" for t in pipeline.TASKS}
    assert len(report["summary"]) == 8  # 8 distinct visit dates


def test_rerun_same_run_id_loads_nothing_new():
    conn = warehouse.connect()
    first = run_demo(conn)
    second = run_demo(conn)
    assert first["loaded"] == 12
    assert second["loaded"] == 0
    assert second["fact_rows"] == 12
    assert second["reconciled"] is True


def test_run_state_records_each_task():
    conn = warehouse.connect()
    run_demo(conn)
    for task in pipeline.TASKS:
        assert pipeline.get_task_status(conn, "demo-test", task) == "done"
