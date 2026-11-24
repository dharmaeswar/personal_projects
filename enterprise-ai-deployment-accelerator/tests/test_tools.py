"""Tests for the MCP-style tool registry."""

import pytest

from enterprise_ai_deployment import (
    DocStore, Document, Tool, ToolRegistry, build_enterprise_tools,
)


def _registry():
    store = DocStore()
    store.add(Document("POL-001", "Password Reset Policy",
                       "Reset passwords through the self-service portal."))
    return build_enterprise_tools(store)


def test_search_kb_tool_returns_hits():
    result = _registry().call("search_kb", query="reset my password")
    assert result[0]["doc_id"] == "POL-001"


def test_lookup_policy_returns_document():
    result = _registry().call("lookup_policy", doc_id="POL-001")
    assert result["title"] == "Password Reset Policy"


def test_lookup_policy_reports_missing_doc():
    result = _registry().call("lookup_policy", doc_id="POL-999")
    assert "error" in result


def test_unknown_tool_rejected():
    with pytest.raises(ValueError):
        _registry().call("delete_everything")


def test_missing_required_input_rejected():
    with pytest.raises(ValueError):
        _registry().call("search_kb")


def test_every_call_is_traced():
    registry = _registry()
    registry.call("search_kb", query="password")
    assert len(registry.trace) == 1
    assert registry.trace[0]["tool"] == "search_kb"


def test_duplicate_tool_registration_rejected():
    registry = ToolRegistry()
    tool = Tool("ping", "Ping.", [], lambda: "pong")
    registry.register(tool)
    with pytest.raises(ValueError):
        registry.register(tool)
