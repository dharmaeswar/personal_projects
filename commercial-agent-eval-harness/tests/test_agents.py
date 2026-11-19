from agent_eval.agents import InvoiceAgent, SupportTriageAgent
from agent_eval.tools import ToolServer
from agent_eval.tracer import Tracer


def _tools():
    return ToolServer(Tracer())


def test_invoice_agent_approves_matching_invoice():
    result = InvoiceAgent(_tools()).process("INV-1001")
    assert result.decision == "approved"
    assert result.trace.tool_names() == ["lookup_invoice", "lookup_po", "approve_invoice"]


def test_invoice_agent_flags_amount_mismatch():
    result = InvoiceAgent(_tools()).process("INV-1002")
    assert result.decision == "flagged"
    assert "amount mismatch" in result.detail
    assert "flag_invoice" in result.trace.tool_names()
    assert "approve_invoice" not in result.trace.tool_names()


def test_invoice_agent_flags_missing_po():
    result = InvoiceAgent(_tools()).process("INV-1004")
    assert result.decision == "flagged"
    assert "PO not found" in result.detail


def test_invoice_agent_unknown_invoice_is_error():
    result = InvoiceAgent(_tools()).process("INV-9999")
    assert result.decision == "error"
    assert len(result.trace.errors()) == 1


def test_invoice_agent_trace_is_scoped_to_the_run():
    tools = _tools()
    agent = InvoiceAgent(tools)
    agent.process("INV-1001")
    second = agent.process("INV-1003")
    assert second.trace.tool_names() == ["lookup_invoice", "lookup_po", "approve_invoice"]
    assert len(tools.tracer.calls) == 6


def test_triage_resolves_kb_question():
    result = SupportTriageAgent(_tools()).process("TKT-2001")
    assert result.decision == "resolved"
    assert "KB-01" in result.detail
    assert result.trace.tool_names() == ["get_ticket", "search_kb", "resolve_ticket"]


def test_triage_escalates_outage_to_engineering():
    tools = _tools()
    result = SupportTriageAgent(tools).process("TKT-2002")
    assert result.decision == "escalated"
    assert result.trace.tool_names() == ["get_ticket", "escalate_ticket"]
    assert tools._escalations[0]["team"] == "engineering"


def test_triage_escalates_refund_to_billing():
    tools = _tools()
    result = SupportTriageAgent(tools).process("TKT-2003")
    assert result.decision == "escalated"
    assert tools._escalations[0]["team"] == "billing"


def test_triage_unknown_ticket_is_error():
    result = SupportTriageAgent(_tools()).process("TKT-9999")
    assert result.decision == "error"
