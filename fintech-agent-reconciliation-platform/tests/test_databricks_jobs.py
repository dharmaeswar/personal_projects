import pytest

from fintech_agents.databricks_jobs import (
    DataQualityCheck, DatabricksJob, JobTask, TransientError)


def test_row_count_check_pass_and_fail():
    check = DataQualityCheck("rows", "row_count_min", 2)
    assert check.run([{"a": 1}, {"a": 2}])["passed"] is True
    assert check.run([{"a": 1}])["passed"] is False


def test_null_rate_check():
    check = DataQualityCheck("nulls", "null_rate_max", 0.1, column="x")
    rows = [{"x": 1}, {"x": None}] + [{"x": 1}] * 8
    assert check.run(rows)["passed"] is True
    assert check.run([{"x": None}, {"x": 1}])["passed"] is False


def test_freshness_check():
    check = DataQualityCheck("fresh", "freshness_max_hours", 24)
    assert check.run([], age_hours=2)["passed"] is True
    assert check.run([], age_hours=30)["passed"] is False


def test_unknown_check_kind_rejected():
    with pytest.raises(ValueError, match="unknown check kind"):
        DataQualityCheck("bad", "nope", 1).run([])


def test_job_runs_tasks_in_dependency_order():
    seen = []

    def maker(name):
        return lambda ctx: seen.append(name) or {"ok": True}

    job = DatabricksJob("close", [
        JobTask("extract", maker("extract")),
        JobTask("transform", maker("transform"), ["extract"]),
        JobTask("load", maker("load"), ["transform"]),
    ])
    result = job.run()
    assert result["status"] == "succeeded"
    assert seen == ["extract", "transform", "load"]
    assert [r["task"] for r in result["run_history"]] == seen


def test_transient_failure_retried_then_succeeds():
    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientError("source hiccup")
        return {"rows": 5}

    job = DatabricksJob("etl", [JobTask("load", flaky, max_retries=2)])
    result = job.run()
    assert result["status"] == "succeeded"
    assert attempts["n"] == 3
    assert len(result["run_history"]) == 3


def test_persistent_failure_stops_job():
    def always_fails(ctx):
        raise TransientError("down")

    job = DatabricksJob("etl", [
        JobTask("extract", always_fails, max_retries=1),
        JobTask("load", lambda ctx: {"ok": True}, ["extract"]),
    ])
    result = job.run()
    assert result["status"] == "failed"
    assert result["failed_task"] == "extract"
    assert "load" not in result["results"]


def test_failed_quality_check_marks_job():
    check = DataQualityCheck("rows", "row_count_min", 10)
    job = DatabricksJob("etl", [
        JobTask("load", lambda ctx: {"rows": [{"a": 1}]}),
    ], checks=[check])
    result = job.run({"rows": [{"a": 1}]})
    assert result["status"] == "checks_failed"
    assert result["checks"][0]["passed"] is False
