"""The gateway itself: authenticate -> authorize -> route -> execute.

Every agent action passes four gates, in order, and every outcome --
allowed or denied -- is written to the audit log:

1. Token: the capability token must verify (signature, expiry, not revoked).
2. Scope: the token's scopes must cover the requested action:resource.
3. Policy: the token's role must allow the action on the resource.
4. Server: the target remote server must exist and be healthy.

Retries are idempotent: repeating a request with the same idempotency
key returns the original result without re-executing the action.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .audit import AuditLog
from .policy import PolicyEngine
from .registry import ServerRegistry
from .tokens import CapabilityToken, TokenStore


@dataclass
class ExecutionResult:
    allowed: bool
    reason: str
    action: str
    resource: str
    server_id: str
    actor: str = ""
    result: str = ""
    replayed: bool = False


class AccessGateway:
    def __init__(self, token_store: TokenStore | None = None,
                 policy: PolicyEngine | None = None,
                 registry: ServerRegistry | None = None,
                 audit: AuditLog | None = None):
        self.tokens = token_store or TokenStore()
        self.policy = policy or PolicyEngine()
        self.registry = registry or ServerRegistry()
        self.audit = audit or AuditLog()
        self._idempotency: dict[str, ExecutionResult] = {}
        self.executed_actions: list[ExecutionResult] = []

    def _deny(self, actor: str, action: str, resource: str, server_id: str,
              reason: str) -> ExecutionResult:
        self.audit.record(actor, action, resource, server_id, "denied", reason)
        return ExecutionResult(False, reason, action, resource, server_id, actor)

    def execute(self, token: str, action: str, resource: str, server_id: str,
                idempotency_key: str | None = None,
                payload: dict | None = None) -> ExecutionResult:
        # Gate 0 -- idempotency: a replayed key returns the first result.
        if idempotency_key and idempotency_key in self._idempotency:
            first = self._idempotency[idempotency_key]
            return ExecutionResult(**{**first.__dict__, "replayed": True})

        # Gate 1 -- token authentication.
        try:
            record: CapabilityToken = self.tokens.verify(token)
        except ValueError as exc:
            return self._deny("unknown", action, resource, server_id, str(exc))

        # Gate 2 -- token scope must cover action:resource.
        scope = f"{action}:{resource}"
        if scope not in record.scopes and f"{action}:*" not in record.scopes:
            return self._deny(record.agent, action, resource, server_id,
                              f"token scope does not cover {scope}")

        # Gate 3 -- role policy (least privilege).
        if not self.policy.allowed(record.role, action, resource):
            return self._deny(record.agent, action, resource, server_id,
                              f"role {record.role!r} may not {action} {resource}")

        # Gate 4 -- target server must exist, be in the token's environment,
        # and be healthy.
        server = self.registry.get(server_id)
        if server is None:
            return self._deny(record.agent, action, resource, server_id,
                              f"unknown remote server {server_id!r}")
        if server.environment != record.environment:
            return self._deny(record.agent, action, resource, server_id,
                              f"server is in {server.environment!r}, token is scoped to "
                              f"{record.environment!r}")
        if not server.healthy:
            return self._deny(record.agent, action, resource, server_id,
                              f"remote server {server_id!r} is unhealthy")

        outcome = ExecutionResult(
            True, "allowed", action, resource, server_id, record.agent,
            result=(f"{action} {resource} executed on {server.name} "
                    f"({server.endpoint})"))
        self.audit.record(record.agent, action, resource, server_id,
                          "allowed", "all gates passed")
        self.executed_actions.append(outcome)
        if idempotency_key:
            self._idempotency[idempotency_key] = outcome
        return outcome
