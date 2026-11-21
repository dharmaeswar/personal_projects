"""Tenant-scoped in-memory store for claims.

Every record carries a ``tenant_id``. Reads and listings always take a
tenant and only ever return that tenant's rows; a cross-tenant access
raises ``PermissionError`` instead of leaking another tenant's data.
This is the multi-tenancy boundary the service layer and the API both
enforce.
"""
from __future__ import annotations


class ClaimStore:
    """In-memory claim store with strict tenant isolation."""

    def __init__(self) -> None:
        self._claims: dict[str, dict] = {}

    def put(self, claim: dict) -> None:
        self._claims[claim["claim_id"]] = claim

    def get(self, claim_id: str, tenant_id: str) -> dict:
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Unknown claim: {claim_id}")
        if claim["tenant_id"] != tenant_id:
            raise PermissionError(
                f"Claim {claim_id} belongs to tenant {claim['tenant_id']}, "
                f"not {tenant_id}")
        return claim

    def list_for_tenant(self, tenant_id: str) -> list[dict]:
        return [c for c in self._claims.values() if c["tenant_id"] == tenant_id]

    def count(self) -> int:
        return len(self._claims)
