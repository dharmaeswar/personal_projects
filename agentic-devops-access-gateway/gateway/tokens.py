"""Scoped capability tokens for DevOps agents.

A token binds an agent identity to a role, a narrow set of scopes
(action:resource pairs), one target environment, and an expiry time.
Tokens are signed with HMAC-SHA256 so a token cannot be forged or
edited after issue; only the token id and a hash are stored server-side,
never the token itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class CapabilityToken:
    token_id: str
    agent: str
    role: str
    scopes: list[str]
    environment: str
    expires_at: float
    revoked: bool = False


class TokenStore:
    """Issues, verifies and revokes scoped capability tokens."""

    def __init__(self, secret: bytes | None = None):
        self._secret = secret or secrets.token_bytes(32)
        self._tokens: dict[str, CapabilityToken] = {}
        self._hashes: dict[str, str] = {}

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    @staticmethod
    def _unb64(text: str) -> bytes:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

    def issue(self, agent: str, role: str, scopes: list[str],
              environment: str, ttl_seconds: int = 3600,
              now: float | None = None) -> str:
        """Mint a token. ``scopes`` are ``action:resource`` strings."""
        issued_at = now if now is not None else time.time()
        token_id = secrets.token_hex(8)
        payload = {
            "id": token_id, "agent": agent, "role": role,
            "scopes": sorted(set(scopes)), "env": environment,
            "exp": issued_at + ttl_seconds,
        }
        raw = json.dumps(payload, sort_keys=True).encode()
        sig = hmac.new(self._secret, raw, hashlib.sha256).digest()
        token = self._b64(raw) + "." + self._b64(sig)
        self._tokens[token_id] = CapabilityToken(
            token_id=token_id, agent=agent, role=role,
            scopes=payload["scopes"], environment=environment,
            expires_at=payload["exp"])
        self._hashes[token_id] = hashlib.sha256(token.encode()).hexdigest()
        return token

    def verify(self, token: str, now: float | None = None) -> CapabilityToken:
        """Verify signature, expiry and revocation. Raises ValueError."""
        check_at = now if now is not None else time.time()
        try:
            raw_b64, sig_b64 = token.split(".")
            raw, sig = self._unb64(raw_b64), self._unb64(sig_b64)
        except (ValueError, Exception) as exc:
            raise ValueError("malformed token") from exc
        expected = hmac.new(self._secret, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad token signature")
        payload = json.loads(raw.decode())
        record = self._tokens.get(payload["id"])
        if record is None:
            raise ValueError("unknown token")
        if record.revoked:
            raise ValueError("token revoked")
        if check_at >= payload["exp"]:
            raise ValueError("token expired")
        if hashlib.sha256(token.encode()).hexdigest() != self._hashes[payload["id"]]:
            raise ValueError("token mismatch")
        return record

    def revoke(self, token_id: str) -> bool:
        """Revoke a token by id. Returns False when the id is unknown."""
        record = self._tokens.get(token_id)
        if record is None:
            return False
        record.revoked = True
        return True

    def token_id(self, token: str) -> str:
        raw_b64 = token.split(".")[0]
        return json.loads(self._unb64(raw_b64).decode())["id"]
