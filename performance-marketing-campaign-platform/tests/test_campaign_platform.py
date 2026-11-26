"""Tests for the Performance Marketing Campaign Platform."""

import pandas as pd
import pytest

from campaign_platform import ai_assist, ingest, orchestration, pacing, planning, quality, warehouse
from campaign_platform.infra import render_main_tf, terraform_config

CAMPAIGNS = [
    {"campaign_id": "c1", "platform": "google_ads", "total_budget": 14000.0,
     "flight_start": "2026-10-01", "flight_end": "2026-10-14", "target_cpa": 40.0},
    {"campaign_id": "c2", "platform": "meta", "total_budget": 7000.0,
     "flight_start": "2026-10-01", "flight_end": "2026-10-07", "target_cpa": 35.0},
]


# --- ingest ---

def test_generate_rows_cover_all_platforms():
    for platform in ingest.PLATFORMS:
        rows = ingest.generate_platform_rows(platform, ["c1"], n_days=3)
        assert len(rows) == 3
        for col in ingest.native_columns(platform):
            assert col in rows[0]


def test_generate_rows_are_deterministic():
    a = ingest.generate_platform_rows("meta", ["c1"], n_days=5)
    b = ingest.generate_platform_rows("meta", ["c1"], n_days=5)
    assert a == b


def test_validate_contract_quarantines_bad_rows():
    rows = [
        {"campaign_id": "c1", "date": "2026-10-01", "impressions": 100,
         "clicks": 5, "spend": 10.0, "actions": 1},
        {"campaign_id": "c1", "date": "2026-10-02", "impressions": 100,
         "clicks": 150, "spend": 10.0, "actions": 1},  # clicks > impressions
        {"campaign_id": "c1", "date": "2026-10-03", "impressions": 100,
         "clicks": 5, "spend": -3.0, "actions": 1},  # negative spend
        {"campaign_id": "c1", "date": "2026-10-04", "impressions": 100,
         "clicks": 5, "actions": 1},  # missing spend
    ]
    valid, bad = ingest.validate_contract(rows, "meta")
    assert len(valid) == 1 and len(bad) == 3
    assert all("_quarantine_reason" in row for row in bad)


def test_normalize_maps_native_fields_to_common_schema():
    rows = ingest.generate_platform_rows("dv360", ["c1"], n_days=2)
    frame = ingest.normalize(rows, "dv360")
    assert list(frame.columns) == ingest.COMMON_COLUMNS
    assert (frame["platform"] == "dv360").all()
    assert (frame["spend"] > 0).all()


def test_dedupe_keeps_last_row():
    frame = pd.DataFrame([
        {"date": "2026-10-01", "platform": "meta", "campaign_id": "c1",
         "impressions": 10, "clicks": 1, "spend": 1.0, "conversions": 0.0},
        {"date": "2026-10-01", "platform": "meta", "campaign_id": "c1",
         "impressions": 20, "clicks": 2, "spend": 2.0, "conversions": 1.0},
    ])
    out = ingest.dedupe(frame)
    assert len(out) == 1 and out.iloc[0]["impressions"] == 20


# --- planning ---

def test_flight_days_inclusive():
    assert planning.flight_days("2026-10-01", "2026-10-14") == 14
    assert planning.flight_days("2026-10-01", "2026-10-01") == 1
    with pytest.raises(ValueError):
        planning.flight_days("2026-10-14", "2026-10-01")


def test_build_plan_daily_budget_and_expected_conversions():
    plan = planning.build_plan(CAMPAIGNS)
    assert plan[0]["flight_days"] == 14
    assert plan[0]["daily_budget"] == 1000.0
    assert plan[0]["expected_daily_conversions"] == 25.0
    assert plan[1]["daily_budget"] == 1000.0


def test_build_plan_rejects_bad_inputs():
    bad = dict(CAMPAIGNS[0], total_budget=0)
    with pytest.raises(ValueError):
        planning.build_plan([bad])
    bad = dict(CAMPAIGNS[0], target_cpa=-1)
    with pytest.raises(ValueError):
        planning.build_plan([bad])
    bad = {k: v for k, v in CAMPAIGNS[0].items() if k != "target_cpa"}
    with pytest.raises(ValueError):
        planning.build_plan([bad])


def test_allocate_budget_reweights_and_preserves_total():
    plan = planning.build_plan(CAMPAIGNS)
    new_plan = planning.allocate_budget(plan, {"google_ads": 0.25, "meta": 0.75})
    assert sum(r["total_budget"] for r in new_plan) == pytest.approx(21000.0)
    assert new_plan[0]["total_budget"] == 5250.0
    assert new_plan[1]["daily_budget"] == pytest.approx(2250.0)


def test_allocate_budget_rejects_bad_weights():
    plan = planning.build_plan(CAMPAIGNS)
    with pytest.raises(ValueError):
        planning.allocate_budget(plan, {"google_ads": 0.5, "meta": 0.4})
    with pytest.raises(ValueError):
        planning.allocate_budget(plan, {"google_ads": 1.0})


# --- pacing ---

def test_pacing_on_track_ahead_behind():
    row = planning.build_plan(CAMPAIGNS)[0]  # daily budget 1000, 14 days
    assert pacing.pacing_status(row, 5000.0, 5)["status"] == "on-track"
    assert pacing.pacing_status(row, 6500.0, 5)["status"] == "ahead"
    assert pacing.pacing_status(row, 3500.0, 5)["status"] == "behind"


def test_pacing_rejects_out_of_flight_day():
    row = planning.build_plan(CAMPAIGNS)[0]
    with pytest.raises(ValueError):
        pacing.pacing_status(row, 100.0, 15)


def test_guardrails_allow_clean_day():
    row = planning.build_plan(CAMPAIGNS)[0]
    result = pacing.optimisation_guardrails(
        row, {"spend": 900.0, "conversions": 25, "impressions": 50000, "clicks": 1200})
    assert result["decision"] == "ALLOW"
    assert result["requires_human_review"] is False


def test_guardrails_hold_on_spend_spike():
    row = planning.build_plan(CAMPAIGNS)[0]
    result = pacing.optimisation_guardrails(
        row, {"spend": 2500.0, "conversions": 25, "impressions": 50000, "clicks": 1200})
    assert result["decision"] == "HOLD"
    assert any("spike" in r for r in result["reasons"])
    assert result["requires_human_review"] is True


def test_guardrails_hold_on_high_cpa_and_zero_clicks():
    row = planning.build_plan(CAMPAIGNS)[0]  # target CPA 40, hold above 60
    high_cpa = pacing.optimisation_guardrails(
        row, {"spend": 1000.0, "conversions": 10, "impressions": 50000, "clicks": 1200})
    assert high_cpa["decision"] == "HOLD"
    assert any("CPA" in r for r in high_cpa["reasons"])
    no_clicks = pacing.optimisation_guardrails(
        row, {"spend": 500.0, "conversions": 5, "impressions": 50000, "clicks": 0})
    assert no_clicks["decision"] == "HOLD"


# --- quality ---

def _clean_frame():
    return pd.DataFrame([
        {"date": "2026-10-01", "platform": "meta", "campaign_id": "c1",
         "impressions": 1000, "clicks": 40, "spend": 50.0, "conversions": 2.0},
        {"date": "2026-10-02", "platform": "meta", "campaign_id": "c1",
         "impressions": 2000, "clicks": 80, "spend": 90.0, "conversions": 3.0},
    ])


def test_run_checks_pass_on_clean_frame():
    results = quality.run_checks(_clean_frame(), {"c1"})
    assert all(r["passed"] for r in results)


def test_run_checks_catch_duplicates_unknown_and_bad_ranges():
    frame = _clean_frame()
    bad = pd.DataFrame([
        {"date": "2026-10-01", "platform": "meta", "campaign_id": "c1",
         "impressions": 1000, "clicks": 40, "spend": 50.0, "conversions": 2.0},
        {"date": "2026-10-03", "platform": "meta", "campaign_id": "cX",
         "impressions": 100, "clicks": 200, "spend": -5.0, "conversions": 1.0},
    ])
    results = {r["check"]: r for r in quality.run_checks(
        pd.concat([frame, bad], ignore_index=True), {"c1"})}
    assert results["uniqueness"]["failed_rows"] == 1
    assert results["ranges"]["failed_rows"] == 1
    assert results["referential_integrity"]["failed_rows"] == 1


def test_quarantine_splits_with_reasons():
    frame = pd.DataFrame([
        {"date": "2026-10-01", "platform": "meta", "campaign_id": "c1",
         "impressions": 1000, "clicks": 40, "spend": 50.0, "conversions": 2.0},
        {"date": "2026-10-02", "platform": "meta", "campaign_id": "c1",
         "impressions": 100, "clicks": 150, "spend": 50.0, "conversions": 2.0},
    ])
    clean, bad = quality.quarantine(frame, {"c1"})
    assert len(clean) == 1 and len(bad) == 1
    assert "clicks exceed impressions" in bad.iloc[0]["_quarantine_reason"]


# --- warehouse ---

def test_medallion_writes_and_gold_metrics(tmp_path):
    clean = _clean_frame()
    result = warehouse.write_medallion(clean, clean, tmp_path)
    assert result["bronze_rows"] == 2 and result["silver_rows"] == 2
    assert result["gold_rows"] == 2
    gold = pd.read_parquet(result["gold"])
    assert gold.iloc[0]["ctr"] == pytest.approx(0.04)
    assert gold.iloc[0]["cpa"] == pytest.approx(25.0)


def test_scd2_budget_change_closes_and_opens_row():
    dim = warehouse.build_campaign_dim(CAMPAIGNS)
    assert all(r["is_current"] for r in dim)
    updated = warehouse.apply_budget_change(dim, "c1", 20000.0, "2026-10-08")
    c1_rows = [r for r in updated if r["campaign_id"] == "c1"]
    assert len(c1_rows) == 2
    old, new = c1_rows
    assert old["is_current"] is False and old["effective_to"] == "2026-10-08"
    assert new["is_current"] is True and new["total_budget"] == 20000.0
    assert sum(1 for r in updated if r["is_current"]) == 2


# --- ai_assist ---

def test_summary_draft_is_human_gated_and_evaluates_clean():
    findings = [
        {"kind": "pacing", "campaign_id": "c1", "detail": "behind: variance -30%"},
        {"kind": "guardrail", "campaign_id": "c2", "decision": "HOLD",
         "detail": "spend spike"},
    ]
    draft = ai_assist.summarize_findings(findings)
    assert draft["requires_human_review"] is True
    assert draft["status"] == "draft"
    assert ai_assist.evaluate_summary(draft, findings)["passed"] is True


def test_evaluation_fails_when_held_campaign_unnamed():
    findings = [{"kind": "guardrail", "campaign_id": "c2", "decision": "HOLD",
                 "detail": "spend spike"}]
    draft = {"summary": "Pipeline findings: 1 item(s) need review.",
             "kinds_covered": ["guardrail"], "finding_count": 1}
    result = ai_assist.evaluate_summary(draft, findings)
    assert result["passed"] is False
    assert result["held_campaigns_unnamed"] == ["c2"]


# --- orchestration ---

def test_dag_runs_in_dependency_order_and_retries():
    calls = []

    def ok(ctx):
        calls.append("ok")

    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        calls.append("flaky")

    tasks = [
        orchestration.DagTask("a", ok),
        orchestration.DagTask("b", flaky, ("a",)),
        orchestration.DagTask("c", ok, ("b",)),
    ]
    result = orchestration.run_dag(tasks, {})
    assert result["success"] is True
    assert result["order"] == ["a", "b", "c"]
    assert result["tasks"]["b"]["attempts"] == 2
    assert calls == ["ok", "flaky", "ok"]


def test_dag_skips_downstream_on_failure_and_detects_cycles():
    def boom(ctx):
        raise RuntimeError("boom")

    def ok(ctx):
        pass

    tasks = [orchestration.DagTask("a", boom),
             orchestration.DagTask("b", ok, ("a",))]
    result = orchestration.run_dag(tasks, {})
    assert result["success"] is False
    assert result["tasks"]["b"]["status"] == "skipped"
    with pytest.raises(ValueError):
        orchestration.topological_order([
            orchestration.DagTask("a", ok, ("b",)),
            orchestration.DagTask("b", ok, ("a",)),
        ])


# --- infra ---

def test_terraform_config_and_render():
    config = terraform_config("prod")
    assert config["resource"]["aws_glue_job"]["ingest"]["number_of_workers"] == 5
    assert config["resource"]["databricks_workspace"]["main"]["sku"] == "premium"
    hcl = render_main_tf(config)
    assert 'resource "aws_s3_bucket" "bronze"' in hcl
    assert 'resource "databricks_workspace" "main"' in hcl
    with pytest.raises(ValueError):
        terraform_config("qa")
