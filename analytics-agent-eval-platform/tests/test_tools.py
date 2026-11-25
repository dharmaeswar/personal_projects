"""Tests for the MCP-style tool server: schemas, validation, tracing."""

import pytest

from agent_eval.sandbox import Sandbox
from agent_eval.tools import ToolServer


@pytest.fixture
def server():
    return ToolServer(Sandbox())


def test_describe_dataset_tool(server):
    call = server.call("describe_dataset", {})
    assert call.ok
    assert "posts" in call.result["tables"]
    assert call.cost_usd >= 0


def test_unknown_tool_fails_but_is_traced(server):
    call = server.call("no_such_tool", {})
    assert not call.ok
    assert "unknown tool" in call.error
    assert len(server.trace) == 1


def test_missing_required_argument_rejected(server):
    call = server.call("text_to_sql", {})
    assert not call.ok
    assert "missing required argument" in call.error


def test_wrong_argument_type_rejected(server):
    call = server.call("text_to_sql", {"question": 42})
    assert not call.ok
    assert "must be a string" in call.error


def test_run_query_tool_returns_provenance(server):
    call = server.call("run_query", {"sql": "SELECT COUNT(*) FROM posts"})
    assert call.ok
    assert call.result["provenance"]["dataset_version"]


def test_totals_count_failures(server):
    server.call("describe_dataset", {})
    server.call("no_such_tool", {})
    totals = server.totals()
    assert totals["calls"] == 2
    assert totals["failed"] == 1
