"""Tenant registry, quotas, and isolation checks.

Every Action belongs to exactly one tenant. Tenants never see each
other's actions, secrets, cache entries, or audit records: every lookup
is scoped by tenant_id and cross-tenant access is denied, not filtered.
"""

from dataclasses import dataclass, field


@dataclass
class Tenant:
    tenant_id: str
    name: str
    max_actions: int = 20
    max_invocations_per_minute: int = 1000
    max_secrets: int = 10


class TenantRegistry:
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}

    def create(self, tenant: Tenant) -> Tenant:
        if tenant.tenant_id in self._tenants:
            raise ValueError(f"tenant {tenant.tenant_id!r} already exists")
        self._tenants[tenant.tenant_id] = tenant
        return tenant

    def get(self, tenant_id: str) -> Tenant:
        try:
            return self._tenants[tenant_id]
        except KeyError:
            raise ValueError(f"unknown tenant {tenant_id!r}") from None

    def exists(self, tenant_id: str) -> bool:
        return tenant_id in self._tenants


def check_same_tenant(owner_tenant_id: str, accessor_tenant_id: str) -> None:
    """Deny any cross-tenant access. Called before every scoped read."""
    if owner_tenant_id != accessor_tenant_id:
        raise PermissionError(
            f"tenant {accessor_tenant_id!r} may not access "
            f"tenant {owner_tenant_id!r} resources"
        )
