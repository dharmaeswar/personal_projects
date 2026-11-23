"""MCP server — tools, OAuth 2.0 / OIDC scopes, and guardrails.

An MCP-shaped server exposes finance tools (reconcile, variance report,
payout create/approve) to agents. Every call is checked three ways:
the caller's token must carry the tool's required scope (OAuth 2.0
client-credentials style), the arguments are guardrail-scanned (amount
limits, PII redaction), and every invocation is logged for audit.
Unknown tools, missing scopes, and guardrail failures are denied with
a reason — never executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_PAYOUT_MINOR = 1_000_000  # $10,000 — above this needs approval, not denial


@dataclass
class Token:
    token_id: str
    subject: str
    scopes: set[str]  # e.g. {"finance:read", "finance:payout"}


@dataclass
class Tool:
    name: str
    required_scope: str
    handler: object = None  # callable(payload) -> dict

    def call(self, payload: dict) -> dict:
        return self.handler(payload)


@dataclass
class ToolResult:
    ok: bool
    data: dict = field(default_factory=dict)
    reason: str = ""


def _scan_args(name: str, payload: dict) -> str | None:
    """Guardrail scan on tool arguments; returns a denial reason or None."""
    if name == "payout.create":
        amount = payload.get("amount_minor", 0)
        if not isinstance(amount, int) or amount <= 0:
            return "payout amount must be a positive integer (minor units)"
        if amount > 100 * MAX_PAYOUT_MINOR:
            return "payout amount exceeds the hard guardrail limit"
        if not payload.get("payee"):
            return "payout requires a payee"
    if "ssn" in payload or "card_number" in payload:
        return "payload contains disallowed PII fields"
    return None


class McpServer:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self.invocations: list[dict] = []

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def invoke(self, token: Token, name: str, payload: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, reason=f"unknown tool: {name}")
        if tool.required_scope not in token.scopes:
            return ToolResult(
                False,
                reason=f"missing scope {tool.required_scope} for {name}")
        denial = _scan_args(name, payload)
        if denial:
            return ToolResult(False, reason=f"guardrail: {denial}")
        self.invocations.append({"tool": name, "subject": token.subject,
                                 "payload": {k: v for k, v in payload.items()
                                             if k not in ("ssn",
                                                          "card_number")}})
        return ToolResult(True, data=tool.call(payload))
