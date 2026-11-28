from genai_platform.agents import Tool, demo_agent


def test_read_tool_returns_borrower_figures():
    agent = demo_agent()
    result = agent.call_tool("lookup_borrower", borrower="BlueRock")
    assert result["ok"] is True
    assert result["result"]["debt"] == 42_000_000
    assert result["result"]["ebitda"] == 14_000_000


def test_covenant_check_flags_breach():
    agent = demo_agent()
    result = agent.call_tool(
        "check_covenant", debt=42_000_000, ebitda=14_000_000
    )
    assert result["result"]["ratio"] == 3.0
    assert result["result"]["breach"] is False
    breached = agent.call_tool(
        "check_covenant", debt=50_000_000, ebitda=10_000_000
    )
    assert breached["result"]["breach"] is True


def test_consequential_action_needs_approval():
    agent = demo_agent()
    refused = agent.call_tool("send_payment", amount=50000)
    assert refused["ok"] is False
    assert "human approval" in refused["error"]
    approved = agent.call_tool("send_payment", approved=True, amount=50000)
    assert approved["ok"] is True


def test_missing_scope_refuses_tool():
    agent = demo_agent()
    agent.tools.append(
        Tool(name="admin_reset", scopes=["admin:write"], description="Reset.")
    )
    result = agent.call_tool("admin_reset")
    assert result["ok"] is False
    assert "missing scopes" in result["error"]


def test_unknown_tool_is_refused_and_logged():
    agent = demo_agent()
    result = agent.call_tool("drop_database")
    assert result["ok"] is False
    assert any(
        entry["kind"] == "tool_call_refused" for entry in agent.audit_log
    )


def test_audit_log_records_prompt_tool_call_and_output():
    agent = demo_agent()
    agent.call_tool(
        "lookup_borrower",
        prompt="Check BlueRock leverage.",
        borrower="Harborline",
    )
    kinds = {entry["kind"] for entry in agent.audit_log}
    assert {"prompt", "tool_call", "output"} <= kinds
    assert agent.audit_summary()["entries"] == len(agent.audit_log)
