"""Caller context: authentication, authorization, and tenant propagation.

Every tool call carries a CallerContext. The context is created once at the
edge (from an API key, OAuth token, or service-to-service identity) and then
propagated unchanged through every adapter and downstream call, so an
agent-invoked call never carries more privilege than the user it acts for.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ContextError(Exception):
    """Raised when a caller context is missing, expired, or insufficient."""


@dataclass(frozen=True)
class CallerContext:
    """Identity and authorization carried across an integration boundary."""

    user_id: str
    tenant_id: str
    scopes: frozenset = field(default_factory=frozenset)
    auth_mechanism: str = "api_key"  # api_key | oauth | service_identity
    request_id: str = ""
    trace_id: str = ""

    def require_scopes(self, *needed: str) -> None:
        """Fail unless the caller holds every needed scope."""
        missing = [s for s in needed if s not in self.scopes]
        if missing:
            raise ContextError(
                f"caller {self.user_id} lacks scopes: {', '.join(missing)}"
            )

    def child(self, *, request_id: str = "", trace_id: str = "") -> "CallerContext":
        """Propagate the same identity to a downstream call.

        Scopes, tenant, and user are copied verbatim; only the per-call
        request/trace ids change. Privilege can never grow downstream.
        """
        return CallerContext(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            scopes=self.scopes,
            auth_mechanism=self.auth_mechanism,
            request_id=request_id or self.request_id,
            trace_id=trace_id or self.trace_id,
        )

    def for_tenant(self, tenant_id: str) -> "CallerContext":
        """Return a context scoped to another tenant — always denied.

        Tenant context is immutable: a caller may never re-scope itself to a
        different tenant. Cross-tenant work needs a fresh context issued for
        that tenant, never a mutation of this one.
        """
        raise ContextError(
            f"tenant context is immutable: cannot move {self.tenant_id} "
            f"to {tenant_id}"
        )
