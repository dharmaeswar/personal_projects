"""Tests for the Comms Data Platform."""

import json

import pandas as pd
import pytest

from comms_platform.catalog import Catalog
from comms_platform.connectors import (
    InternalCommsSource,
    TransientVendorError,
    VendorAPIClient,
    fetch_all_vendor_metrics,
)
from comms_platform.iac import build_stack, validate_stack
from comms_platform.lake import Lake, SchemaViolation
from comms_platform.observability import (
    evaluate_alarms,
    orr_checklist,
    run_canaries,
)
from comms_platform.orchestration import (
    StateMachine,
    StepFailed,
    TransientStepError,
)
from comms_platform.pipeline import run_pipeline
from comms_platform.quality import (
    check_messages,
    check_metrics,
    reconcile_gold_to_silver,
    retry_quarantined,
)
from comms_platform.query import QueryEngine, UnsafeQuery
from comms_platform.serving import CommsDataAPI, MCPServer
from comms_platform.transforms import build_daily_engagement


# --- connectors -----------------------------------------------------------

def test_internal_source_returns_seeded_messages():
    rows = InternalCommsSource().fetch_messages()
    assert len(rows) == 15  # 12 good + 3 planted bad
    assert len({r["message_id"] for r in rows}) == 14  # one duplicate id


def test_vendor_client_paginates_all_rows():
    rows = fetch_all_vendor_metrics(VendorAPIClient())
    assert len(rows) == 14  # 12 good + 2 planted bad


def test_vendor_client_retries_transient_failure():
    client = VendorAPIClient()
    page1 = client.fetch_page(None)
    assert len(page1["rows"]) == 5
    with pytest.raises(TransientVendorError):
        client.fetch_page("5")  # first attempt on page 2 fails
    page2 = client.fetch_page("5")  # retry succeeds
    assert len(page2["rows"]) == 5


def test_vendor_client_rate_limit():
    client = VendorAPIClient()
    client.calls = 20
    with pytest.raises(TransientVendorError):
        client.fetch_page(None)


# --- lake -----------------------------------------------------------------

def test_lake_write_read_roundtrip(tmp_path):
    lake = Lake(tmp_path / "lake")
    df = pd.DataFrame(
        {
            "message_id": ["MSG-1"],
            "campaign_id": ["CMP-101"],
            "campaign_name": ["Test"],
            "channel": ["email"],
            "subject": ["Hi"],
            "send_date": ["2026-11-10"],
            "audience_size": [100],
        }
    )
    lake.write_table("bronze", "messages", df)
    out = lake.read_table("bronze", "messages")
    assert len(out) == 1
    assert out.iloc[0]["message_id"] == "MSG-1"
    assert len(lake.log_entries("bronze", "messages")) == 1


def test_lake_rejects_schema_violation(tmp_path):
    lake = Lake(tmp_path / "lake")
    bad = pd.DataFrame({"message_id": ["MSG-1"]})  # missing columns
    with pytest.raises(SchemaViolation):
        lake.write_table("bronze", "messages", bad)


def test_lake_missing_table_raises(tmp_path):
    lake = Lake(tmp_path / "lake")
    with pytest.raises(FileNotFoundError):
        lake.read_table("gold", "daily_engagement")


# --- quality --------------------------------------------------------------

def _raw_messages():
    return pd.DataFrame(InternalCommsSource().fetch_messages())


def test_check_messages_quarantines_all_planted_bad_rows():
    clean, quarantined = check_messages(_raw_messages())
    assert len(clean) == 12
    assert len(quarantined) == 3
    reasons = sorted(quarantined["quarantine_reason"].tolist())
    assert reasons == [
        "duplicate message_id",
        "null campaign_id",
        "send_date after 2026-12-31",
    ]


def test_check_metrics_quarantines_bad_rows():
    rows = fetch_all_vendor_metrics(VendorAPIClient())
    clean, quarantined = check_metrics(pd.DataFrame(rows))
    assert len(clean) == 12
    assert len(quarantined) == 2
    reasons = sorted(quarantined["quarantine_reason"].tolist())
    assert reasons == ["negative metric value", "unknown campaign_id"]


def test_retry_quarantined_promotes_fixed_row():
    _, quarantined = check_messages(_raw_messages())
    fixed = [
        {
            "message_id": "MSG-1013",
            "campaign_id": "CMP-101",
            "campaign_name": "Orphan Message",
            "channel": "email",
            "subject": "Orphan — update 1",
            "send_date": "2026-11-15",
            "audience_size": 1200,
        }
    ]
    promoted, still = retry_quarantined(quarantined, fixed)
    assert len(promoted) == 1
    assert len(still) == 2


def test_retry_quarantined_keeps_unfixed_rows():
    _, quarantined = check_messages(_raw_messages())
    promoted, still = retry_quarantined(quarantined, [])
    assert len(promoted) == 0
    assert len(still) == 3


# --- transforms -----------------------------------------------------------

def test_build_daily_engagement_aggregates():
    clean_messages, _ = check_messages(_raw_messages())
    clean_metrics, _ = check_metrics(pd.DataFrame(fetch_all_vendor_metrics(VendorAPIClient())))
    gold = build_daily_engagement(clean_messages, clean_metrics)
    assert set(gold.columns) == {
        "event_date",
        "campaign_id",
        "channel",
        "messages_sent",
        "total_opens",
        "total_clicks",
        "open_rate",
    }
    assert int(gold["messages_sent"].sum()) == 12
    assert int(gold["total_opens"].sum()) == int(clean_metrics["opens"].sum())
    assert ((gold["open_rate"] >= 0) & (gold["open_rate"] <= 1.5)).all()


def test_reconcile_flags_mismatch():
    clean_messages, _ = check_messages(_raw_messages())
    clean_metrics, _ = check_metrics(pd.DataFrame(fetch_all_vendor_metrics(VendorAPIClient())))
    gold = build_daily_engagement(clean_messages, clean_metrics)
    assert reconcile_gold_to_silver(gold, clean_messages, clean_metrics) == []
    tampered = gold.copy()
    tampered.loc[0, "total_opens"] += 1
    problems = reconcile_gold_to_silver(tampered, clean_messages, clean_metrics)
    assert problems and "total_opens" in problems[0]


# --- catalog --------------------------------------------------------------

def test_catalog_register_search_describe(tmp_path):
    cat = Catalog(tmp_path / "catalog.json")
    cat.register(
        "daily_engagement",
        "Daily engagement by campaign.",
        {"event_date": "string"},
        ["event_date"],
        "s3://x/daily_engagement/",
        "comms-tech",
    )
    assert cat.describe("daily_engagement")["owner"] == "comms-tech"
    assert len(cat.search("engagement")) == 1
    assert cat.search("billing") == []
    assert cat.list_names() == ["daily_engagement"]


def test_catalog_duplicate_register_rejected(tmp_path):
    cat = Catalog(tmp_path / "catalog.json")
    cat.register("d", "desc", {}, [], "s3://x/", "team")
    with pytest.raises(ValueError):
        cat.register("d", "desc", {}, [], "s3://x/", "team")


def test_catalog_describe_unknown_raises(tmp_path):
    cat = Catalog(tmp_path / "catalog.json")
    with pytest.raises(KeyError):
        cat.describe("nope")


# --- query ----------------------------------------------------------------

def _gold_tables():
    clean_messages, _ = check_messages(_raw_messages())
    clean_metrics, _ = check_metrics(pd.DataFrame(fetch_all_vendor_metrics(VendorAPIClient())))
    return {"daily_engagement": build_daily_engagement(clean_messages, clean_metrics)}


def test_query_engine_select():
    engine = QueryEngine(_gold_tables())
    rows = engine.query("SELECT campaign_id, SUM(total_opens) AS opens FROM daily_engagement GROUP BY campaign_id")
    assert len(rows) == 5
    assert all("opens" in r for r in rows)
    engine.close()


def test_query_engine_rejects_writes():
    engine = QueryEngine(_gold_tables())
    with pytest.raises(UnsafeQuery):
        engine.query("DROP TABLE daily_engagement")
    with pytest.raises(UnsafeQuery):
        engine.query("DELETE FROM daily_engagement")
    engine.close()


# --- serving --------------------------------------------------------------

def _api(tmp_path):
    cat = Catalog(tmp_path / "catalog.json")
    cat.register(
        "daily_engagement",
        "Daily engagement by campaign.",
        {"event_date": "string"},
        ["event_date"],
        "s3://x/daily_engagement/",
        "comms-tech",
    )
    return CommsDataAPI(cat, _gold_tables(), quality_report={"quarantined": 5})


def test_api_list_and_describe(tmp_path):
    api = _api(tmp_path)
    assert api.list_datasets() == {"datasets": ["daily_engagement"]}
    assert api.describe_dataset("daily_engagement")["dataset"]["owner"] == "comms-tech"


def test_api_query_and_quality_report(tmp_path):
    api = _api(tmp_path)
    rows = api.query_dataset("SELECT COUNT(*) AS n FROM daily_engagement")["rows"]
    assert rows[0]["n"] > 0
    assert api.get_quality_report() == {"quality": {"quarantined": 5}}


def test_mcp_list_and_call(tmp_path):
    mcp = MCPServer(_api(tmp_path))
    tools = mcp.list_tools()["tools"]
    assert set(tools) == {"list_datasets", "describe_dataset", "query_dataset"}
    result = mcp.call_tool("query_dataset", {"sql": "SELECT COUNT(*) AS n FROM daily_engagement"})
    assert result["result"]["rows"][0]["n"] > 0


def test_mcp_unknown_tool_returns_error(tmp_path):
    mcp = MCPServer(_api(tmp_path))
    assert "error" in mcp.call_tool("drop_table", {})
    assert "error" in mcp.call_tool("query_dataset", {})


def test_mcp_handle_request_envelope(tmp_path):
    mcp = MCPServer(_api(tmp_path))
    resp = mcp.handle_request(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "list_datasets", "arguments": {}}}
    )
    assert resp["id"] == 7
    assert resp["result"]["datasets"] == ["daily_engagement"]
    bad = mcp.handle_request({"jsonrpc": "2.0", "id": 8, "method": "nope"})
    assert bad["error"]["code"] == -32601


# --- orchestration --------------------------------------------------------

def test_state_machine_runs_in_dependency_order(tmp_path):
    seen = []

    def make(name):
        def _fn(ctx):
            seen.append(name)
            return name

        return _fn

    machine = StateMachine(
        [
            {"name": "a", "fn": make("a"), "depends_on": [], "retries": 0},
            {"name": "b", "fn": make("b"), "depends_on": ["a"], "retries": 0},
            {"name": "c", "fn": make("c"), "depends_on": ["b"], "retries": 0},
        ],
        tmp_path / "state.json",
    )
    machine.run("r1", {})
    assert seen == ["a", "b", "c"]


def test_state_machine_retries_transient_then_succeeds(tmp_path):
    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientStepError("boom")
        return "ok"

    machine = StateMachine(
        [{"name": "x", "fn": flaky, "depends_on": [], "retries": 3}],
        tmp_path / "state.json",
    )
    results = machine.run("r1", {})
    assert results["x"] == "ok"
    assert attempts["n"] == 3


def test_state_machine_dead_letters_after_retries(tmp_path):
    def always_fail(ctx):
        raise TransientStepError("boom")

    machine = StateMachine(
        [{"name": "x", "fn": always_fail, "depends_on": [], "retries": 1}],
        tmp_path / "state.json",
    )
    with pytest.raises(StepFailed):
        machine.run("r1", {})
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["runs"]["r1"]["dead_letter"][0]["step"] == "x"


def test_state_machine_cycle_rejected(tmp_path):
    machine = StateMachine(
        [
            {"name": "a", "fn": lambda ctx: None, "depends_on": ["b"], "retries": 0},
            {"name": "b", "fn": lambda ctx: None, "depends_on": ["a"], "retries": 0},
        ],
        tmp_path / "state.json",
    )
    with pytest.raises(ValueError):
        machine.run("r1", {})


# --- IaC ------------------------------------------------------------------

def test_iac_stack_validates():
    stack = build_stack("dev")
    assert validate_stack(stack) == []
    assert len(stack["Resources"]) == 12


def test_iac_stack_missing_property_flagged():
    stack = build_stack("dev")
    del stack["Resources"]["ServingCache"]["Properties"]["TableName"]
    problems = validate_stack(stack)
    assert any("TableName" in p for p in problems)


# --- observability --------------------------------------------------------

def test_canaries_and_orr_pass_after_pipeline(tmp_path):
    run_pipeline(tmp_path)
    lake = Lake(tmp_path / "lake")
    cat = Catalog(tmp_path / "catalog.json")
    canaries = run_canaries(lake, cat)
    assert all(c["passed"] for c in canaries), canaries
    alarms = evaluate_alarms(canaries, 5)
    assert any(a["severity"] == "warning" for a in alarms)  # quarantined rows warn
    assert not any(a["severity"] == "critical" for a in alarms)
    orr = orr_checklist(canaries, alarms, [], cat.list_names())
    assert all(orr.values())


# --- end to end -----------------------------------------------------------

def test_full_pipeline_end_to_end(tmp_path):
    results = run_pipeline(tmp_path)
    assert set(results) == {"ingest", "validate", "transform", "catalog", "observe"}
    assert results["validate"]["quarantined_messages"] == 3
    assert results["validate"]["quarantined_metrics"] == 2
    assert results["transform"]["reconciliation_problems"] == []
    assert results["observe"]["orr_passed"] is True
    assert (tmp_path / "validation_report.txt").exists()
    assert "ORR gate: PASSED" in (tmp_path / "validation_report.txt").read_text()
    lake = Lake(tmp_path / "lake")
    assert lake.table_exists("gold", "daily_engagement")
    assert len(lake.log_entries("gold", "daily_engagement")) == 1
