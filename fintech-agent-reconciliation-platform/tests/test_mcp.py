import pytest

from fintech_agents.mcp import McpServer, Token, Tool


def make_server():
    server = McpServer()
    server.register(Tool("reconcile", "finance:read",
                         lambda p: {"ok": True}))
    server.register(Tool("payout.create", "finance:payout",
                         lambda p: {"payout_id": p["payout_id"]}))
    return server


def test_allowed_call_executes():
    server = make_server()
    token = Token("t1", "agent", {"finance:read"})
    result = server.invoke(token, "reconcile", {})
    assert result.ok is True


def test_unknown_tool_denied():
    server = make_server()
    token = Token("t1", "agent", {"finance:read"})
    result = server.invoke(token, "nope.tool", {})
    assert result.ok is False and "unknown tool" in result.reason


def test_missing_scope_denied():
    server = make_server()
    token = Token("t1", "agent", {"finance:read"})
    result = server.invoke(token, "payout.create",
                           {"payout_id": "p1", "payee": "x",
                            "amount_minor": 100})
    assert result.ok is False and "missing scope" in result.reason


def test_guardrail_rejects_bad_payout_amount():
    server = make_server()
    token = Token("t1", "agent", {"finance:payout"})
    assert server.invoke(token, "payout.create",
                         {"payout_id": "p1", "payee": "x",
                          "amount_minor": 0}).ok is False
    assert server.invoke(token, "payout.create",
                         {"payout_id": "p1", "payee": "x",
                          "amount_minor": -5}).ok is False


def test_guardrail_rejects_pii_in_payload():
    server = make_server()
    token = Token("t1", "agent", {"finance:read"})
    result = server.invoke(token, "reconcile", {"ssn": "123-45-6789"})
    assert result.ok is False and "PII" in result.reason


def test_invocations_logged_without_pii():
    server = make_server()
    token = Token("t1", "agent", {"finance:read"})
    server.invoke(token, "reconcile", {"ledger": ["e1"]})
    assert len(server.invocations) == 1
    assert server.invocations[0]["subject"] == "agent"
