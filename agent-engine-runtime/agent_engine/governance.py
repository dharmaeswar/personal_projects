"""Identity & governance: scoped tool authorization, deny-by-default policy.

Mimics the MCP/A2A shape: tools are registered with the scopes they
require, and an agent identity carries the scopes it was granted. A tool
call is allowed only when (1) the caller's tenant matches the resource's
tenant, (2) the caller holds every scope the tool requires, and (3) no
deny policy matches. Anything not explicitly allowed is denied, and
every decision is logged so governance can audit it later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    principal: str  # agent or user identity, e.g. "agent:support-bot"
    scopes: frozenset = frozenset()


@dataclass
class ToolSpec:
    name: str
    description: str
    required_scopes: frozenset = frozenset()
    fn: Optional[Callable[..., object]] = None


@dataclass
class Policy:
    """One governance rule. effect "deny" wins over "allow"."""

    name: str
    effect: str  # "allow" | "deny"
    tool: Optional[str] = None  # None = applies to every tool
    scope: Optional[str] = None  # None = applies regardless of scope
    tenant: Optional[str] = None  # None = applies to every tenant

    def matches(self, tool: str, scopes: Set[str], tenant_id: str) -> bool:
        if self.tool is not None and self.tool != tool:
            return False
        if self.scope is not None and self.scope not in scopes:
            return False
        if self.tenant is not None and self.tenant != tenant_id:
            return False
        return True


@dataclass
class Decision:
    allowed: bool
    reason: str


class PolicyEngine:
    """Deny-by-default: a call needs an allow and no matching deny."""

    def __init__(self, policies: Optional[List[Policy]] = None):
        self.policies: List[Policy] = list(policies or [])
        self.audit_log: List[Dict[str, object]] = []

    def add(self, policy: Policy) -> None:
        self.policies.append(policy)

    def decide(self, tool: str, ctx: TenantContext) -> Decision:
        scopes = set(ctx.scopes)
        denied = [p for p in self.policies
                  if p.effect == "deny" and p.matches(tool, scopes, ctx.tenant_id)]
        if denied:
            decision = Decision(False, f"denied by policy {denied[0].name}")
        else:
            allowed = [p for p in self.policies
                       if p.effect == "allow" and p.matches(tool, scopes, ctx.tenant_id)]
            if allowed:
                decision = Decision(True, f"allowed by policy {allowed[0].name}")
            else:
                decision = Decision(False, "deny-by-default: no allow policy matches")
        self.audit_log.append({
            "tool": tool, "principal": ctx.principal,
            "tenant": ctx.tenant_id, "allowed": decision.allowed,
            "reason": decision.reason,
        })
        return decision


class ToolRegistry:
    """Tools with required scopes; calls go through tenant + policy checks."""

    def __init__(self, policy_engine: Optional[PolicyEngine] = None):
        self._tools: Dict[str, ToolSpec] = {}
        self.policies = policy_engine or PolicyEngine()

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def tool_names(self) -> List[str]:
        return sorted(self._tools)

    def authorize(self, tool_name: str, ctx: TenantContext,
                  resource_tenant: str) -> Decision:
        spec = self._tools.get(tool_name)
        if spec is None:
            return Decision(False, f"unknown tool {tool_name}")
        if resource_tenant != ctx.tenant_id:
            return Decision(False, "cross-tenant access denied")
        missing = sorted(set(spec.required_scopes) - set(ctx.scopes))
        if missing:
            return Decision(False, f"missing scopes: {', '.join(missing)}")
        return self.policies.decide(tool_name, ctx)

    def call(self, tool_name: str, ctx: TenantContext,
             resource_tenant: str, **kwargs) -> object:
        decision = self.authorize(tool_name, ctx, resource_tenant)
        if not decision.allowed:
            raise PermissionError(f"tool {tool_name} denied: {decision.reason}")
        spec = self._tools[tool_name]
        if spec.fn is None:
            raise ValueError(f"tool {tool_name} has no implementation")
        return spec.fn(**kwargs)
