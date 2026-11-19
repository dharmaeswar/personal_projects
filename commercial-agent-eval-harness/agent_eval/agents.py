"""Two deterministic business-workflow agents.

These are rule-based stand-ins for LLM agents: the *workflow* (which tools
are called, in what order, and what decision follows) is exactly what the
evaluation harness scores. Using deterministic policies keeps every eval
reproducible with no model API calls; swapping in a real Claude Agent SDK
agent means replacing `decide` while the tools, tracer and evals stay put.
"""

from __future__ import annotations

from .tools import ToolError


class AgentResult:
    def __init__(self, agent, input_id, decision, detail, trace):
        self.agent = agent
        self.input_id = input_id
        self.decision = decision
        self.detail = detail
        self.trace = trace

    def to_dict(self):
        return {"agent": self.agent, "input_id": self.input_id,
                "decision": self.decision, "detail": self.detail,
                "trace": self.trace.to_dict()}


class InvoiceAgent:
    """Finance-ops agent: validate an invoice against its PO, then approve or flag."""

    name = "invoice-agent"

    def __init__(self, tools):
        self.tools = tools

    def process(self, invoice_id):
        trace = self.tools.tracer
        start = len(trace.calls)
        try:
            inv = self.tools.call("lookup_invoice", {"invoice_id": invoice_id})
        except ToolError as exc:
            return AgentResult(self.name, invoice_id, "error", str(exc),
                               _slice(trace, start))
        try:
            po = self.tools.call("lookup_po", {"po_id": inv["po_id"]})
        except ToolError as exc:
            self.tools.call("flag_invoice", {"invoice_id": invoice_id,
                                             "reason": f"PO not found: {inv['po_id']}"})
            return AgentResult(self.name, invoice_id, "flagged",
                               f"PO not found: {inv['po_id']}", _slice(trace, start))
        if inv["vendor"] != po["vendor"]:
            reason = f"vendor mismatch: invoice {inv['vendor']} vs PO {po['vendor']}"
            self.tools.call("flag_invoice", {"invoice_id": invoice_id, "reason": reason})
            return AgentResult(self.name, invoice_id, "flagged", reason,
                               _slice(trace, start))
        if abs(inv["amount"] - po["amount"]) > 0.01:
            reason = (f"amount mismatch: invoice ${inv['amount']:.2f} "
                      f"vs PO ${po['amount']:.2f}")
            self.tools.call("flag_invoice", {"invoice_id": invoice_id, "reason": reason})
            return AgentResult(self.name, invoice_id, "flagged", reason,
                               _slice(trace, start))
        if po["status"] != "approved":
            reason = f"PO {po['po_id']} is {po['status']}, not approved"
            self.tools.call("flag_invoice", {"invoice_id": invoice_id, "reason": reason})
            return AgentResult(self.name, invoice_id, "flagged", reason,
                               _slice(trace, start))
        rec = self.tools.call("approve_invoice", {"invoice_id": invoice_id,
                                                   "approver": "invoice-agent"})
        return AgentResult(self.name, invoice_id, "approved",
                           f"approved ${rec['amount']:.2f} against {po['po_id']}",
                           _slice(trace, start))


class SupportTriageAgent:
    """Support-triage agent: classify a ticket, check the KB, resolve or escalate."""

    name = "support-triage-agent"

    OUTAGE_WORDS = ("500", "error", "down", "outage", "fail")
    REFUND_WORDS = ("refund", "duplicate charge", "charged twice")

    def __init__(self, tools):
        self.tools = tools

    def process(self, ticket_id):
        trace = self.tools.tracer
        start = len(trace.calls)
        try:
            tkt = self.tools.call("get_ticket", {"ticket_id": ticket_id})
        except ToolError as exc:
            return AgentResult(self.name, ticket_id, "error", str(exc),
                               _slice(trace, start))
        text = f"{tkt['subject']} {tkt['body']}".lower()
        if any(w in text for w in self.OUTAGE_WORDS):
            self.tools.call("escalate_ticket", {"ticket_id": ticket_id,
                                                 "team": "engineering",
                                                 "reason": "service outage / 5xx errors"})
            return AgentResult(self.name, ticket_id, "escalated",
                               "outage pattern -> engineering", _slice(trace, start))
        if any(w in text for w in self.REFUND_WORDS):
            self.tools.call("escalate_ticket", {"ticket_id": ticket_id,
                                                 "team": "billing",
                                                 "reason": "refund needs finance confirmation"})
            return AgentResult(self.name, ticket_id, "escalated",
                               "refund request -> billing", _slice(trace, start))
        hits = self.tools.call("search_kb", {"query": tkt["subject"]})
        if hits:
            article = hits[0]
            self.tools.call("resolve_ticket",
                            {"ticket_id": ticket_id,
                             "resolution": f"Answered from {article['article_id']}: {article['title']}"})
            return AgentResult(self.name, ticket_id, "resolved",
                               f"resolved via {article['article_id']}",
                               _slice(trace, start))
        self.tools.call("escalate_ticket", {"ticket_id": ticket_id,
                                             "team": "support",
                                             "reason": "no KB article matches"})
        return AgentResult(self.name, ticket_id, "escalated",
                           "no KB match -> support", _slice(trace, start))


def _slice(trace, start):
    """A per-run view of the tracer: only calls made during this agent run."""
    from .tracer import Tracer
    sub = Tracer()
    sub.calls = list(trace.calls[start:])
    return sub
