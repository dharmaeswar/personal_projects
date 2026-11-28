"""MCP server tests: handshake, tool listing, tool calls, errors, read-only use."""
import json
import sqlite3

import pytest

from src.loader import load_reference_data, load_usage_events
from src.mcp_server import TOOL_DESCRIPTIONS, handle_request
from src.model import init_warehouse

ACCOUNTS = [{"account_id": "ACCT-1", "account_name": "A", "account_type": "production",
             "owner_team": "t1", "created_date": "2024-01-01"}]
REGIONS = [{"region_code": "us-east-1", "region_name": "US East", "country": "United States"}]


def _event(eid, date="2026-11-03", cost=4.2, qty=10.0):
    return {"event_id": eid, "account_id": "ACCT-1", "service_code": "COMPUTE",
            "service_name": "Compute Service", "tier": "standard",
            "pricing_model": "on-demand", "region_code": "us-east-1",
            "usage_date": date, "usage_qty": qty, "cost_usd": cost,
            "unit": "vCPU-hours"}


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    conn = init_warehouse(path)
    load_reference_data(conn, ACCOUNTS, REGIONS)
    load_usage_events(conn, [_event("E1"), _event("E2", date="2026-11-04", cost=6.0)], "b1")
    conn.commit()
    conn.close()
    return path


def _call(db_path, method, params=None, req_id=1):
    req = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        req["params"] = params
    return handle_request(req, db_path)


def _tool_text(resp):
    assert "result" in resp, resp
    return json.loads(resp["result"]["content"][0]["text"])


def test_initialize_returns_server_info(db_path):
    resp = _call(db_path, "initialize", {"protocolVersion": "2024-11-05",
                                         "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    assert resp["result"]["serverInfo"]["name"] == "analytics-warehouse"
    assert resp["result"]["capabilities"] == {"tools": {}}


def test_tools_list_names_all_five_tools(db_path):
    resp = _call(db_path, "tools/list")
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == list(TOOL_DESCRIPTIONS)
    assert all(t["inputSchema"]["type"] == "object" for t in resp["result"]["tools"])


def test_warehouse_health_reports_all_checks_passing(db_path):
    payload = _tool_text(_call(db_path, "tools/call",
                               {"name": "warehouse_health", "arguments": {"run_date": "2026-11-05"}}))
    assert payload["all_checks_passed"] is True
    assert {c["name"] for c in payload["checks"]} == {
        "referential_integrity_fact_to_dims", "no_null_or_negative_usage",
        "no_duplicate_events", "scd2_single_current_no_overlap", "freshness_sla"}


def test_analytics_tool_returns_modelled_rows(db_path):
    payload = _tool_text(_call(db_path, "tools/call",
                               {"name": "cost_per_account", "arguments": {}}))
    assert payload["rows_returned"] == 1
    assert payload["rows"][0]["account_id"] == "ACCT-1"
    assert payload["rows"][0]["total_cost_usd"] == pytest.approx(10.2)


def test_limit_is_capped_and_applied(db_path):
    payload = _tool_text(_call(db_path, "tools/call",
                               {"name": "daily_cost_trend", "arguments": {"limit": 1}}))
    assert payload["rows_returned"] == 1
    assert len(payload["rows"]) == 1


def test_unknown_tool_is_a_jsonrpc_error(db_path):
    resp = _call(db_path, "tools/call", {"name": "drop_tables", "arguments": {}})
    assert resp["error"]["code"] == -32602
    assert "unknown tool" in resp["error"]["message"]


def test_unknown_method_is_a_jsonrpc_error(db_path):
    resp = _call(db_path, "resources/list")
    assert resp["error"]["code"] == -32601


def test_bad_limit_is_rejected(db_path):
    resp = _call(db_path, "tools/call",
                 {"name": "daily_cost_trend", "arguments": {"limit": "all"}})
    assert resp["error"]["code"] == -32602


def test_missing_warehouse_is_an_error_not_a_crash(tmp_path):
    resp = _call(str(tmp_path / "nope.db"), "tools/call",
                 {"name": "warehouse_health", "arguments": {}})
    assert resp["error"]["code"] == -32602
    assert "not found" in resp["error"]["message"]


def test_tool_call_does_not_write_to_the_warehouse(db_path):
    before = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) n FROM fact_service_usage").fetchone()[0]
    _call(db_path, "tools/call", {"name": "revenue_driver_by_service_region", "arguments": {}})
    after = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) n FROM fact_service_usage").fetchone()[0]
    assert before == after == 2


def test_notification_returns_none(db_path):
    assert _call(db_path, "notifications/initialized", req_id=None) is None
