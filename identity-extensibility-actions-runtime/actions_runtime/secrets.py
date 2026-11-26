"""Per-tenant secret store.

Secrets are stored per tenant and are only ever handed to the sandbox
while it executes that tenant's own action. Audit and log records carry
the secret *name* only; the value never appears in a log line.
"""

import hashlib


class SecretStore:
    def __init__(self) -> None:
        self._secrets: dict[str, dict[str, str]] = {}

    def put(self, tenant_id: str, name: str, value: str) -> str:
        """Store a secret; returns its SHA-256 fingerprint, not the value."""
        if not name or not value:
            raise ValueError("secret name and value are required")
        self._secrets.setdefault(tenant_id, {})[name] = value
        return hashlib.sha256(f"{tenant_id}:{name}:{value}".encode()).hexdigest()[:16]

    def get(self, tenant_id: str, name: str) -> str:
        try:
            return self._secrets[tenant_id][name]
        except KeyError:
            raise ValueError(f"secret {name!r} not found") from None

    def count(self, tenant_id: str) -> int:
        return len(self._secrets.get(tenant_id, {}))

    def has(self, tenant_id: str, name: str) -> bool:
        return name in self._secrets.get(tenant_id, {})


def redact(value: str) -> str:
    """Redaction used in every log/audit line that mentions a secret."""
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]
