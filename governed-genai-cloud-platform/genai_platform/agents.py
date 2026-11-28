"""Governed agents: least-privilege tools, sandboxed execution, human
approval for consequential actions, and a complete audit log.

An agent is privileged software: every tool it may call carries the
scopes it needs and nothing more, every tool call is sandboxed (the demo
runs tools against seeded in-memory data, never a real system), actions
that move money, change data or contact a customer need a human approval
before they run, and every prompt, tool call and output lands in an audit
log the security and model-risk teams can replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Actions that always need a human approval, whatever the agent's scopes.
CONSEQUENTIAL_ACTIONS = {"send_payment", "update_record", "contact_customer"}


@dataclass
class Tool:
    """One tool an agent may call, with the scopes it requires."""

    name: str
    scopes: list[str]
    consequential: bool = False
    description: str = ""

    def run(self, **kwargs) -> dict:
        """Sandboxed stand-in execution against seeded data."""
        if self.name == "lookup_borrower":
            borrowers = {
                "BlueRock": {"debt": 42_000_000, "ebitda": 14_000_000},
                "Harborline": {"debt": 18_000_000, "ebitda": 9_000_000},
            }
            borrower = kwargs.get("borrower", "")
            if borrower not in borrowers:
                return {"ok": False, "error": f"unknown borrower {borrower}"}
            return {"ok": True, "result": borrowers[borrower]}
        if self.name == "check_covenant":
            debt = kwargs.get("debt", 0)
            ebitda = kwargs.get("ebitda", 0) or 1
            ratio = round(debt / ebitda, 2)
            return {
                "ok": True,
                "result": {
                    "ratio": ratio,
                    "limit": 3.5,
                    "breach": ratio > 3.5,
                },
            }
        if self.name in CONSEQUENTIAL_ACTIONS:
            return {"ok": True, "result": f"{self.name} executed (approved)"}
        return {"ok": True, "result": f"{self.name} ran with {kwargs}"}


@dataclass
class Agent:
    """An agent with a fixed tool set and a fixed scope budget."""

    name: str
    scopes: list[str]
    tools: list[Tool] = field(default_factory=list)
    audit_log: list[dict] = field(default_factory=list)

    def _log(self, kind: str, detail: dict) -> None:
        entry = {"agent": self.name, "kind": kind, **detail}
        self.audit_log.append(entry)

    def can_use(self, tool: Tool) -> bool:
        return all(scope in self.scopes for scope in tool.scopes)

    def call_tool(
        self,
        tool_name: str,
        *,
        approved: bool = False,
        prompt: str = "",
        **kwargs,
    ) -> dict:
        """Call a tool under governance. Returns a result dict; refused
        calls return ``ok: False`` with a reason and are still logged."""
        tool = next((t for t in self.tools if t.name == tool_name), None)
        if tool is None:
            result = {"ok": False, "error": f"tool not registered: {tool_name}"}
            self._log("tool_call_refused", {"tool": tool_name, **result})
            return result
        if not self.can_use(tool):
            result = {
                "ok": False,
                "error": f"missing scopes for {tool_name}: "
                f"{[s for s in tool.scopes if s not in self.scopes]}",
            }
            self._log("tool_call_refused", {"tool": tool_name, **result})
            return result
        if tool.consequential and not approved:
            result = {
                "ok": False,
                "error": f"{tool_name} needs human approval before running",
            }
            self._log("approval_required", {"tool": tool_name, **result})
            return result
        self._log("prompt", {"prompt": prompt, "tool": tool_name})
        outcome = tool.run(**kwargs)
        self._log("tool_call", {"tool": tool_name, "args": kwargs, **outcome})
        if outcome.get("ok"):
            self._log(
                "output", {"tool": tool_name, "output": outcome.get("result")}
            )
        return outcome

    def audit_summary(self) -> dict:
        kinds: dict[str, int] = {}
        for entry in self.audit_log:
            kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
        return {"agent": self.name, "entries": len(self.audit_log), "kinds": kinds}


def demo_agent() -> Agent:
    """A covenant-check agent: read-only lookups plus one consequential
    action that always needs a human."""
    return Agent(
        name="covenant-checker",
        scopes=["borrower:read", "covenant:read", "payment:write"],
        tools=[
            Tool(
                name="lookup_borrower",
                scopes=["borrower:read"],
                description="Read a borrower's debt and EBITDA.",
            ),
            Tool(
                name="check_covenant",
                scopes=["covenant:read"],
                description="Compute the leverage ratio against the 3.5x limit.",
            ),
            Tool(
                name="send_payment",
                scopes=["payment:write"],
                consequential=True,
                description="Send a cure payment — human approval required.",
            ),
        ],
    )
