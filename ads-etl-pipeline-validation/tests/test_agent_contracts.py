"""Tests for the data contracts and the data-ops agent.

The agent is deterministic: the same pipeline run always produces the
same tool calls and the same action plan, so these tests assert exact
counts and exact severities, not just "something happened".
"""

from __future__ import annotations

from ads_etl.agent import (
    AGENTS,
    Orchestrator,
    RunContext,
    tool_check_contract,
    tool_inspect_quarantine,
    tool_lookup_lineage,
    tool_plan_backfill,
    tool_run_quality_checks,
)
from ads_etl.contracts import CONTRACTS, detect_drift, validate_contract
from ads_etl.data import generate_all
from ads_etl.pipeline import build_gold, build_silver, connect, load_bronze
from ads_etl.streaming import EventConsumer, consume_all_in_batches


def _context() -> RunContext:
    data = generate_all()
    campaigns, ads, events = data["campaigns"], data["ads"], data["events"]
    consumer = EventConsumer()
    consumer.produce(events)
    ingested = consume_all_in_batches(consumer, batch_size=100)
    conn = connect(":memory:")
    load_bronze(conn, campaigns, ads, ingested)
    silver, quarantine, silver_lineage = build_silver(
        conn, ingested, ads, campaigns
    )
    gold, gold_lineage = build_gold(conn, silver)
    conn.close()
    return RunContext(
        campaigns=campaigns,
        ads=ads,
        bronze_events=ingested,
        silver=silver,
        quarantine=quarantine,
        gold=gold,
        silver_lineage=silver_lineage,
        gold_lineage=gold_lineage,
    )


# ---------------------------------------------------------- contracts

def test_contract_registry_covers_all_tables():
    assert set(CONTRACTS) == {
        "events_bronze",
        "events_silver",
        "gold_daily_spend",
    }
    for contract in CONTRACTS.values():
        assert contract.version == 1
        assert contract.owner.startswith("dsp-analytics")


def test_silver_contract_holds_on_clean_run():
    ctx = _context()
    violations = validate_contract(ctx.silver, CONTRACTS["events_silver"])
    assert violations == []


def test_gold_contract_holds_on_clean_run():
    ctx = _context()
    violations = validate_contract(ctx.gold, CONTRACTS["gold_daily_spend"])
    assert violations == []


def test_contract_catches_missing_column():
    ctx = _context()
    rows = [dict(r) for r in ctx.silver[:3]]
    del rows[0]["spend_usd"]
    violations = validate_contract(rows, CONTRACTS["events_silver"])
    assert any("missing column: spend_usd" in v.problem for v in violations)


def test_contract_catches_extra_column_and_bad_range():
    ctx = _context()
    rows = [dict(r) for r in ctx.silver[:3]]
    rows[0]["surprise_col"] = "new field from producer"
    rows[1]["spend_usd"] = -5.0
    violations = validate_contract(rows, CONTRACTS["events_silver"])
    problems = [v.problem for v in violations]
    assert any("unexpected column: surprise_col" in p for p in problems)
    assert any("spend_usd=-5.0 outside" in p for p in problems)


def test_contract_catches_wrong_type_and_null():
    ctx = _context()
    rows = [dict(r) for r in ctx.silver[:3]]
    rows[0]["impressions"] = "many"
    rows[1]["campaign_id"] = None
    violations = validate_contract(rows, CONTRACTS["events_silver"])
    problems = [v.problem for v in violations]
    assert any("impressions" in p and "str" in p for p in problems)
    assert any("nulls in non-nullable column campaign_id" in p for p in problems)


def test_drift_detects_added_and_removed_columns():
    ctx = _context()
    rows = [dict(r) for r in ctx.silver[:3]]
    rows[0]["new_metric"] = 1
    for r in rows:
        del r["cpc_usd"]
    drift = detect_drift(rows, CONTRACTS["events_silver"])
    assert drift["added_columns"] == ["new_metric"]
    assert drift["removed_columns"] == ["cpc_usd"]
    assert drift["type_changes"] == []


def test_drift_detects_type_change():
    ctx = _context()
    rows = [dict(r) for r in ctx.silver[:3]]
    for r in rows:
        r["impressions"] = str(r["impressions"])
    drift = detect_drift(rows, CONTRACTS["events_silver"])
    assert any("impressions" in t for t in drift["type_changes"])


# -------------------------------------------------------------- agent

def test_three_agents_with_named_tools():
    assert [a.name for a in AGENTS] == [
        "ingest-agent",
        "quality-agent",
        "governance-agent",
    ]
    assert "run_quality_checks" in AGENTS[0].tools
    assert "inspect_quarantine" in AGENTS[1].tools
    assert "plan_backfill" in AGENTS[2].tools


def test_quality_checks_tool_reports_planted_failures():
    ctx = _context()
    call = tool_run_quality_checks(ctx)
    assert call.agent == "ingest-agent"
    assert "of 10 bronze checks passed" in call.summary
    assert any("FAIL" in f for f in call.findings)


def test_quarantine_tool_groups_reasons():
    ctx = _context()
    call = tool_inspect_quarantine(ctx)
    assert call.summary.startswith("14 quarantined rows")
    assert any("duplicate event_id" in f for f in call.findings)


def test_contract_tool_reports_no_violations_on_silver():
    ctx = _context()
    call = tool_check_contract(ctx, "events_silver")
    assert call.summary.startswith("0 contract violations")


def test_lineage_tool_finds_silver_event_and_gold_groups():
    ctx = _context()
    event_id = ctx.silver[0]["event_id"]
    call = tool_lookup_lineage(ctx, event_id)
    assert "found" in call.summary
    assert any("feeds" in f for f in call.findings)


def test_lineage_tool_reports_quarantined_event_as_absent():
    ctx = _context()
    silver_ids = {r["event_id"] for r in ctx.silver}
    quarantined_only = [
        r for r in ctx.quarantine if r["event_id"] not in silver_ids
    ]
    assert quarantined_only  # the planted bad rows include unique ids
    event_id = quarantined_only[0]["event_id"]
    call = tool_lookup_lineage(ctx, event_id)
    assert "not in silver" in call.summary


def test_backfill_tool_counts_late_and_quarantined():
    ctx = _context()
    call = tool_plan_backfill(ctx)
    assert "2 late-arriving rows already in silver" in call.findings[0]
    assert "14 quarantined rows excluded" in call.findings[1]


def test_orchestrator_plan_is_deterministic_and_actionable():
    ctx = _context()
    first = Orchestrator().run(ctx).to_dict()
    second = Orchestrator().run(ctx).to_dict()
    assert first == second
    assert len(first["tool_calls"]) == 6  # 2 + 1 + 3 across the agents
    severities = [a["severity"] for a in first["actions"]]
    assert "block" in severities  # failing bronze checks block promotion
    assert "fix" in severities  # top quarantine cause gets a fix action
    assert "watch" in severities  # late-arriving rows get a watch action
    for action in first["actions"]:
        assert action["evidence"]  # every action names its evidence


def test_orchestrator_plan_is_clean_when_data_is_clean():
    ctx = _context()
    # Keep only the first occurrence of each silver event_id: the raw
    # ingest also holds the later duplicate rows that silver rejected.
    seen: set[str] = set()
    clean_bronze = []
    for row in ctx.bronze_events:
        if row["event_id"] in {s["event_id"] for s in ctx.silver} and row["event_id"] not in seen:
            seen.add(row["event_id"])
            clean_bronze.append(row)
    ctx.bronze_events = clean_bronze
    ctx.quarantine = []
    for row in ctx.silver:
        row["late_arriving"] = 0
    plan = Orchestrator().run(ctx)
    assert plan.actions == []
    assert "none" in plan.render_text().lower()
