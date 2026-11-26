"""Tests for the DAG job orchestrator."""

import time

import pytest

from posttrade.orchestrator import Job, run_dag, topological_levels


def ok_job(name, deps=None, result="done"):
    return Job(name, lambda ctx: result, deps=deps or [])


def test_levels_respect_dependencies():
    jobs = [ok_job("c", ["a", "b"]), ok_job("a"), ok_job("b", ["a"])]
    levels = topological_levels(jobs)
    assert [[j.name for j in level] for level in levels] == [["a"], ["b"], ["c"]]


def test_parallel_level_runs_all_jobs():
    jobs = [ok_job("a"), ok_job("b"), ok_job("c")]
    report = run_dag(jobs, max_workers=3)
    assert report.ok
    assert report.succeeded == 3
    assert {name: r.result for name, r in report.results.items()} == {
        "a": "done", "b": "done", "c": "done",
    }


def test_job_sees_dependency_results_in_context():
    jobs = [
        Job("ingest", lambda ctx: [1, 2, 3]),
        Job("count", lambda ctx: len(ctx["ingest"]), deps=["ingest"]),
    ]
    report = run_dag(jobs)
    assert report.ok
    assert report.results["count"].result == 3


def test_retry_then_success():
    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient failure")
        return "recovered"

    report = run_dag([Job("flaky", flaky, max_retries=1)])
    assert report.ok
    assert report.results["flaky"].attempts == 2
    assert report.results["flaky"].result == "recovered"


def test_failure_after_retries_and_downstream_skipped():
    jobs = [
        Job("bad", lambda ctx: 1 / 0, max_retries=1),
        Job("downstream", lambda ctx: "never", deps=["bad"]),
        ok_job("independent"),
    ]
    report = run_dag(jobs)
    assert not report.ok
    assert report.results["bad"].status == "FAILED"
    assert report.results["bad"].attempts == 2
    assert "ZeroDivisionError" in report.results["bad"].error
    assert report.results["downstream"].status == "SKIPPED"
    assert report.results["downstream"].attempts == 0
    assert report.results["independent"].status == "SUCCEEDED"


def test_cycle_raises():
    jobs = [ok_job("a", ["b"]), ok_job("b", ["a"])]
    with pytest.raises(ValueError, match="cycle"):
        run_dag(jobs)


def test_unknown_dependency_raises():
    with pytest.raises(ValueError, match="unknown job"):
        run_dag([ok_job("a", ["missing"])])


def test_duplicate_name_raises():
    with pytest.raises(ValueError, match="duplicate job name"):
        run_dag([ok_job("a"), ok_job("a")])


def test_durations_recorded():
    def slow(ctx):
        time.sleep(0.02)
        return None

    report = run_dag([Job("slow", slow)])
    assert report.results["slow"].duration_seconds >= 0.02


def test_failed_job_counts():
    report = run_dag([Job("bad", lambda ctx: 1 / 0, max_retries=0)])
    assert report.failed == 1 and report.succeeded == 0 and report.skipped == 0
