"""MCP-style tool registry with authorization boundaries.

Each tool declares the scopes an agent needs to call it. Sensitive tools
add an extra check: their arguments are scanned by the guardrails, so a
prompt-injection payload smuggled into a tool call is denied even when
the agent holds the scope. Every call is recorded for the monitor.
"""
from dataclasses import dataclass, field

from .guardrails import evaluate_tool_args


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    scopes: frozenset
    sensitive: bool = False


@dataclass
class CallRecord:
    tool: str
    allowed: bool
    reason: str
    args: dict = field(default_factory=dict)


REGISTRY = [
    Tool("search_kb", "Search the support knowledge base", frozenset({"read:kb"})),
    Tool("lookup_invoice", "Look up one invoice by id", frozenset({"read:finance"})),
    Tool("lookup_customer", "Look up one customer record", frozenset({"read:customer"})),
    Tool("approve_invoice", "Approve a matched invoice", frozenset({"write:finance"})),
    Tool("resolve_ticket", "Resolve a support ticket", frozenset({"write:support"})),
    Tool("escalate_ticket", "Escalate a ticket to engineering",
         frozenset({"write:support"})),
    Tool("refund_customer", "Issue a customer refund", frozenset({"write:finance"}),
         sensitive=True),
    Tool("export_data", "Export records out of the system",
         frozenset({"read:export"}), sensitive=True),
    Tool("delete_record", "Delete a record permanently",
         frozenset({"write:admin"}), sensitive=True),
    Tool("send_email", "Send an email to an outside address",
         frozenset({"write:comms"}), sensitive=True),
]


class ToolRegistry:
    def __init__(self, tools=None):
        self.tools = {t.name: t for t in (tools or REGISTRY)}
        self.calls = []

    def call(self, agent_scopes, tool_name, args=None):
        args = args or {}
        tool = self.tools.get(tool_name)
        if tool is None:
            rec = CallRecord(tool_name, False, "unknown-tool", args)
            self.calls.append(rec)
            return rec
        missing = set(tool.scopes) - set(agent_scopes)
        if missing:
            rec = CallRecord(tool_name, False,
                             "missing-scope:" + ",".join(sorted(missing)), args)
            self.calls.append(rec)
            return rec
        if tool.sensitive:
            check = evaluate_tool_args(tool_name, args)
            if check.blocked:
                rec = CallRecord(tool_name, False,
                                 "guardrail:" + ",".join(check.reasons), args)
                self.calls.append(rec)
                return rec
        rec = CallRecord(tool_name, True, "ok", args)
        self.calls.append(rec)
        return rec
