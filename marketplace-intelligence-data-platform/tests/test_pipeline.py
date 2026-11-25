"""Tests for sources and the end-to-end pipeline: retry on a flaky
API page, DAG ordering/retry/cycle detection, and a full seeded run
that is idempotent on re-run."""

from pathlib import Path

import pytest

from marketintel.pipeline import run_dag, run_pipeline, topological_order
from marketintel.sources import CsvFeedSource, JsonApiSource
from marketintel.warehouse import connect
from marketintel import warehouse
from marketintel.pipeline import Task

DATA = Path(__file__).resolve().parent.parent / "data"


def test_csv_source_reads_seeded_feed():
    result = CsvFeedSource("v1", DATA / "competitor_prices_v1.csv", "v1").fetch()
    assert len(result.records) == 8
    assert result.records[0].schema_version == "v1"


def test_json_api_retries_transient_failure_once():
    pages = [{"records": [{"a": 1}]}, {"records": [{"a": 2}]}]
    result = JsonApiSource("api", pages, "v1", fail_on_page=1).fetch()
    assert len(result.records) == 2
    assert result.pages_fetched == 2
    assert result.retries == 1


def test_dag_respects_dependencies_and_retries_once(tmp_path):
    conn = connect(str(tmp_path / "dag.sqlite"))
    calls = {"flaky": 0}
    order = []

    def flaky():
        calls["flaky"] += 1
        if calls["flaky"] == 1:
            raise RuntimeError("transient")
        order.append("flaky")

    def after():
        order.append("after")

    results = run_dag(
        [Task("after", after, ["flaky"]), Task("flaky", flaky)],
        conn, "run-1",
    )
    assert results == {"flaky": "done", "after": "done"}
    assert calls["flaky"] == 2
    assert order == ["flaky", "after"]
    # Re-running the same run_id skips completed tasks (recovery).
    results2 = run_dag(
        [Task("after", after, ["flaky"]), Task("flaky", flaky)],
        conn, "run-1",
    )
    assert results2 == {"flaky": "skipped", "after": "skipped"}
    conn.close()


def test_dag_cycle_detected():
    with pytest.raises(ValueError, match="cycle"):
        topological_order([Task("a", lambda: None, ["b"]),
                           Task("b", lambda: None, ["a"])])


def test_full_pipeline_seeded_run(tmp_path):
    db = str(tmp_path / "market.sqlite")
    report = run_pipeline(DATA, db, run_id="test-run")
    assert report["raw_records"] == 19
    assert report["quality"]["checked"] == 19
    assert report["quality"]["quarantined"] == 4
    assert report["quality"]["loaded"] == 15
    assert report["inserted"] == 15
    assert report["reconciliation"]["rows_match"] is True
    assert report["reconciliation"]["totals_match"] is True
    assert report["api_retries"] == 1
    assert report["review_queue_pending"] >= 1  # zone_name fuzzy mapping
    assert report["contract"]["errors"] == []
    assert report["dag"]["publish"] == "done"
    assert len(report["daily_avg_price"]) > 0


def test_full_pipeline_rerun_is_idempotent(tmp_path):
    db = str(tmp_path / "market.sqlite")
    run_pipeline(DATA, db, run_id="run-1")
    report = run_pipeline(DATA, db, run_id="run-2")
    assert report["inserted"] == 0
    assert report["reconciliation"]["rows_match"] is True
    assert warehouse.fact_count(connect(db)) == 15
