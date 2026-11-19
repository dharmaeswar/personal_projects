"""Evaluation suites: acceptance criteria for the agents.

Each EvalCase states the expected decision, the tools the agent must call,
and latency/cost budgets. A case passes only if the decision matches, every
required tool was called, no tool errored, and the budgets hold. The suite
result is the acceptance gate a customer would sign off against.
"""

from __future__ import annotations


class EvalCase:
    def __init__(self, case_id, agent_name, input_id, expected_decision,
                 required_tools, max_latency_ms=1000, max_cost_usd=0.01,
                 note="", allowed_error_tools=()):
        self.case_id = case_id
        self.agent_name = agent_name
        self.input_id = input_id
        self.expected_decision = expected_decision
        self.required_tools = required_tools
        self.max_latency_ms = max_latency_ms
        self.max_cost_usd = max_cost_usd
        self.note = note
        # Tools whose error is the expected path for this case (e.g. a
        # lookup for a record that does not exist), not a failure.
        self.allowed_error_tools = tuple(allowed_error_tools)


class CaseResult:
    def __init__(self, case, result):
        self.case = case
        self.result = result
        self.failures = []
        if result is None:
            self.failures.append("no result returned")
            return
        if result.decision != case.expected_decision:
            self.failures.append(
                f"decision {result.decision!r} != expected {case.expected_decision!r}")
        called = result.trace.tool_names()
        for tool in case.required_tools:
            if tool not in called:
                self.failures.append(f"required tool not called: {tool}")
        if result.trace.errors():
            unexpected = [e for e in result.trace.errors()
                          if e.tool not in case.allowed_error_tools]
            if unexpected:
                self.failures.append(
                    f"{len(unexpected)} tool error(s): "
                    + "; ".join(e.error or e.tool for e in unexpected))
        if result.trace.total_latency_ms() > case.max_latency_ms:
            self.failures.append(
                f"latency {result.trace.total_latency_ms()}ms exceeds "
                f"budget {case.max_latency_ms}ms")
        if result.trace.total_cost_usd() > case.max_cost_usd:
            self.failures.append(
                f"cost ${result.trace.total_cost_usd():.6f} exceeds "
                f"budget ${case.max_cost_usd:.6f}")

    @property
    def passed(self):
        return not self.failures

    def to_dict(self):
        return {"case_id": self.case.case_id, "agent": self.case.agent_name,
                "input_id": self.case.input_id,
                "expected": self.case.expected_decision,
                "actual": self.result.decision if self.result else None,
                "passed": self.passed, "failures": self.failures,
                "latency_ms": self.result.trace.total_latency_ms() if self.result else 0,
                "cost_usd": self.result.trace.total_cost_usd() if self.result else 0,
                "tools_called": self.result.trace.tool_names() if self.result else []}


INVOICE_CASES = [
    EvalCase("INV-OK-1", "invoice-agent", "INV-1001", "approved",
             ["lookup_invoice", "lookup_po", "approve_invoice"],
             note="Invoice matches its PO exactly."),
    EvalCase("INV-OK-2", "invoice-agent", "INV-1003", "approved",
             ["lookup_invoice", "lookup_po", "approve_invoice"],
             note="Second clean invoice, different vendor."),
    EvalCase("INV-AMT-1", "invoice-agent", "INV-1002", "flagged",
             ["lookup_invoice", "lookup_po", "flag_invoice"],
             note="Invoice $980 vs PO $875: amount mismatch must be flagged."),
    EvalCase("INV-PO-1", "invoice-agent", "INV-1004", "flagged",
             ["lookup_invoice", "lookup_po", "flag_invoice"],
             note="PO-9999 does not exist: flag, do not approve.",
             allowed_error_tools=["lookup_po"]),
    EvalCase("INV-DUP-1", "invoice-agent", "INV-1005", "approved",
             ["lookup_invoice", "lookup_po", "approve_invoice"],
             note="Same invoice/PO pair as INV-1001, re-processed cleanly."),
]

TRIAGE_CASES = [
    EvalCase("TRI-HOWTO-1", "support-triage-agent", "TKT-2001", "resolved",
             ["get_ticket", "search_kb", "resolve_ticket"],
             note="Password-reset question has a KB article: resolve."),
    EvalCase("TRI-HOWTO-2", "support-triage-agent", "TKT-2004", "resolved",
             ["get_ticket", "search_kb", "resolve_ticket"],
             note="Usage-export question has a KB article: resolve."),
    EvalCase("TRI-OUTAGE-1", "support-triage-agent", "TKT-2002", "escalated",
             ["get_ticket", "escalate_ticket"],
             note="500 errors after deploy: escalate to engineering, no KB lookup."),
    EvalCase("TRI-REFUND-1", "support-triage-agent", "TKT-2003", "escalated",
             ["get_ticket", "escalate_ticket"],
             note="Duplicate-charge refund: escalate to billing, no KB lookup."),
]


def run_suite(agent, cases):
    """Run every case through one agent; returns (results, summary dict)."""
    results = []
    for case in cases:
        result = agent.process(case.input_id)
        results.append(CaseResult(case, result))
    passed = sum(1 for r in results if r.passed)
    summary = {
        "agent": agent.name,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "total_latency_ms": sum(r.result.trace.total_latency_ms()
                                for r in results if r.result),
        "total_cost_usd": round(sum(r.result.trace.total_cost_usd()
                                    for r in results if r.result), 6),
    }
    return results, summary
