"""Per-tenant cache with TTL.

Actions may cache small results (a looked-up user tier, a feature flag)
between invocations. Entries are namespaced by tenant so one tenant can
never read — or poison — another tenant's cached values.
"""

import time


class TenantCache:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[object, float]] = {}

    @staticmethod
    def _key(tenant_id: str, key: str) -> str:
        return f"{tenant_id}:{key}"

    def put(self, tenant_id: str, key: str, value: object, ttl_seconds: int = 300) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._entries[self._key(tenant_id, key)] = (value, time.time() + ttl_seconds)

    def get(self, tenant_id: str, key: str):
        entry = self._entries.get(self._key(tenant_id, key))
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._entries[self._key(tenant_id, key)]
            return None
        return value
