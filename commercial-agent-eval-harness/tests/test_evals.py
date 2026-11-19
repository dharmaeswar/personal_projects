from agent_eval.agents import InvoiceAgent, SupportTriageAgent
from agent_eval.evals import (INVOICE_CASES, TRIAGE_CASES, EvalCase,
                              run_suite)
from agent_eval.tools import ToolServer
from agent_eval.tracer import Tracer


def _run_all():
    tools = ToolServer(Tracer())
    inv_results, inv_summary = run_suite(InvoiceAgent(tools), INVOICE_CASES)
    tri_results, tri_summary = run_suite(SupportTriageAgent(tools), TRIAGE_CASES)
    return inv_results, inv_summary, tri_results, tri_summary


def test_full_suites_pass():
    inv_results, inv_summary, tri_results, tri_summary = _run_all()
    assert inv_summary == {"agent": "invoice-agent", "total": 5, "passed": 5,
                           "failed": 0, "pass_rate": 1.0,
                           "total_latency_ms": 715,
                           "total_cost_usd": 0.0048}
    assert tri_summary["passed"] == 4 and tri_summary["total"] == 4
    assert all(r.passed for r in inv_results + tri_results)


def test_wrong_expected_decision_fails():
    tools = ToolServer(Tracer())
    case = EvalCase("X-1", "invoice-agent", "INV-1001", "flagged",
                    ["lookup_invoice", "lookup_po", "approve_invoice"])
    results, _ = run_suite(InvoiceAgent(tools), [case])
    assert not results[0].passed
    assert any("decision 'approved' != expected 'flagged'" in f
               for f in results[0].failures)


def test_missing_required_tool_fails():
    tools = ToolServer(Tracer())
    case = EvalCase("X-2", "support-triage-agent", "TKT-2002", "escalated",
                    ["get_ticket", "escalate_ticket", "search_kb"])
    results, _ = run_suite(SupportTriageAgent(tools), [case])
    assert not results[0].passed
    assert any("required tool not called: search_kb" in f
               for f in results[0].failures)


def test_latency_budget_breach_fails():
    tools = ToolServer(Tracer())
    case = EvalCase("X-3", "invoice-agent", "INV-1001", "approved",
                    ["lookup_invoice", "lookup_po", "approve_invoice"],
                    max_latency_ms=10)
    results, _ = run_suite(InvoiceAgent(tools), [case])
    assert not results[0].passed
    assert any("exceeds budget 10ms" in f for f in results[0].failures)


def test_cost_budget_breach_fails():
    tools = ToolServer(Tracer())
    case = EvalCase("X-4", "support-triage-agent", "TKT-2001", "resolved",
                    ["get_ticket", "search_kb", "resolve_ticket"],
                    max_cost_usd=0.0001)
    results, _ = run_suite(SupportTriageAgent(tools), [case])
    assert not results[0].passed
    assert any("exceeds budget" in f for f in results[0].failures)


def test_allowed_tool_error_does_not_fail_case():
    tools = ToolServer(Tracer())
    case = EvalCase("X-5", "invoice-agent", "INV-1004", "flagged",
                    ["lookup_invoice", "lookup_po", "flag_invoice"],
                    allowed_error_tools=["lookup_po"])
    results, _ = run_suite(InvoiceAgent(tools), [case])
    assert results[0].passed
    assert results[0].failures == []


def test_case_result_dict_shape():
    tools = ToolServer(Tracer())
    results, _ = run_suite(InvoiceAgent(tools), INVOICE_CASES[:1])
    d = results[0].to_dict()
    assert d["case_id"] == "INV-OK-1"
    assert d["passed"] is True
    assert d["tools_called"] == ["lookup_invoice", "lookup_po", "approve_invoice"]
    assert d["latency_ms"] == 145
