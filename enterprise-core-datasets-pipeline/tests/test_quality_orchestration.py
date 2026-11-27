"""Tests for quality checks, orchestration, backfill, and analytics."""

import pytest

from enterprise_core import analytics, seed as seed_mod
from enterprise_core.backfill import plan_backfill, run_backfill
from enterprise_core.orchestration import DagRunner, Task
from enterprise_core.pipeline import Warehouse
from enterprise_core.quality import all_passed, run_checks


def _loaded_wh():
    wh = Warehouse()
    feeds = seed_mod.seed_all()
    for feed, rows in feeds.items():
        wh.ingest(feed, rows)
    wh.build_dims()
    wh.build_facts()
    return wh


# ---- quality ------------------------------------------------------------
def test_all_checks_pass_on_clean_run():
    wh = _loaded_wh()
    checks = run_checks(wh)
    assert len(checks) >= 15
    assert all_passed(checks), [c for c in checks if not c["passed"]]


def test_reconciliation_catches_tampered_fact():
    wh = _loaded_wh()
    fact = wh.tables["fact_ai_usage_daily"]
    fact.loc[fact.index[0], "cost_usd"] += 100.0
    checks = run_checks(wh)
    failed = [c["check"] for c in checks if not c["passed"]]
    assert "reconciliation:fact_ai_cost_vs_bronze" in failed


def test_freshness_fails_on_stale_fact():
    wh = _loaded_wh()
    ue = wh.tables["fact_unit_economics_daily"]
    wh.tables["fact_unit_economics_daily"] = ue[ue["date"] < "2026-11-20"]
    checks = run_checks(wh)
    failed = {c["check"] for c in checks if not c["passed"]}
    assert "freshness:fact_unit_economics_daily" in failed


# ---- orchestration ------------------------------------------------------
def test_dag_respects_dependencies():
    seen = []

    def mk(name):
        return lambda: seen.append(name) or name

    tasks = [Task("a", [], mk("a")),
             Task("b", ["a"], mk("b")),
             Task("c", ["b"], mk("c"))]
    DagRunner(tasks).run("r1", {})
    assert seen == ["a", "b", "c"]


def test_dag_retries_transient_failure_once():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return "ok"

    results = DagRunner([Task("flaky", [], flaky, transient=True)]).run("r1", {})
    assert results["flaky"] == "ok"
    assert calls["n"] == 2


def test_dag_does_not_retry_permanent_failure():
    def broken():
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError):
        DagRunner([Task("broken", [], broken)]).run("r1", {})


def test_dag_resume_skips_completed_tasks():
    calls = {"n": 0}

    def work():
        calls["n"] += 1
        return calls["n"]

    runner = DagRunner([Task("work", [], work)])
    runner.run("r1", {"work": {"seed": 42}})
    runner.run("r1", {"work": {"seed": 42}})
    assert calls["n"] == 1  # second run resumed, did not redo the work
    runner.run("r1", {"work": {"seed": 43}})
    assert calls["n"] == 2  # changed inputs redo the task


def test_dag_rejects_cycle():
    tasks = [Task("a", ["b"], lambda: None), Task("b", ["a"], lambda: None)]
    with pytest.raises(ValueError, match="cycle"):
        DagRunner(tasks).run("r1", {})


# ---- backfill -----------------------------------------------------------
def test_backfill_plan_uses_lineage():
    wh = _loaded_wh()
    plan = plan_backfill(wh, "ai_usage", "2026-11-01", "2026-11-07")
    assert plan["affected_facts"] == ["fact_ai_usage_daily"]
    assert "bronze_jira_issues" not in plan["lineage"]["fact_ai_usage_daily"]


def test_backfill_recomputes_same_totals_and_commits():
    wh = _loaded_wh()
    before = float(wh.tables["fact_ai_usage_daily"]["cost_usd"].sum())
    report = run_backfill(wh, "ai_usage", "2026-11-10", "2026-11-12")
    assert report["cutover"] == "committed"
    assert report["checks_passed"]
    after = float(wh.tables["fact_ai_usage_daily"]["cost_usd"].sum())
    assert abs(before - after) < 0.01


def test_backfill_rolls_back_on_failed_checks():
    wh = _loaded_wh()
    # Corrupt bronze so the rebuilt range fails reconciliation.
    bronze = wh.tables["bronze_ai_usage"]
    mask = bronze["event_date"] == "2026-11-11"
    wh.tables["bronze_ai_usage"] = bronze.copy()
    wh.tables["bronze_ai_usage"].loc[mask, "cost_usd"] = -1.0
    report = run_backfill(wh, "ai_usage", "2026-11-11", "2026-11-11")
    assert report["cutover"] == "rolled back"
    assert not report["checks_passed"]


# ---- analytics ----------------------------------------------------------
def test_analytics_tie_to_facts():
    wh = _loaded_wh()
    by_tool = analytics.ai_cost_by_tool_month(wh)
    assert abs(by_tool["cost_usd"].sum()
               - wh.tables["fact_ai_usage_daily"]["cost_usd"].sum()) < 0.01
    by_team = analytics.ai_cost_by_team(wh)
    assert abs(by_team["share_pct"].sum() - 100.0) < 0.05
    gvr = analytics.gbv_vs_revenue(wh)
    assert 10.0 < gvr["revenue_share_of_gbv_pct"][0] < 15.0
    assert 0.0 < gvr["avg_margin_pct"][0] < 100.0
    throughput = analytics.jira_throughput(wh)
    assert not throughput.empty
    assert (throughput["done_points"] >= 0).all()
