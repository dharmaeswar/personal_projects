"""API-key authentication for the model gateway.

Keys carry scopes, a tier (which sets default rate budgets), an expiry,
and a revoked flag. Only SHA-256 hashes of keys are stored.
"""

import hashlib
import secrets
import time

SCOPES = ("models:invoke", "usage:read", "billing:read")

TIERS = ("free", "pro", "scale")


def hash_key(raw_key):
    """Return the SHA-256 hex digest of a raw API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ApiKey:
    def __init__(self, key_id, owner, tier, scopes, expires_at=None):
        if tier not in TIERS:
            raise ValueError("unknown tier: %r" % tier)
        bad = [s for s in scopes if s not in SCOPES]
        if bad:
            raise ValueError("unknown scopes: %r" % (bad,))
        self.key_id = key_id
        self.owner = owner
        self.tier = tier
        self.scopes = tuple(scopes)
        self.expires_at = expires_at  # epoch seconds, or None for no expiry
        self.revoked = False
        self.key_hash = None

    def has_scope(self, scope):
        return scope in self.scopes

    def is_usable(self, now=None):
        now = time.time() if now is None else now
        if self.revoked:
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        return True


class KeyStore:
    """In-memory store mapping key hashes to ApiKey records."""

    def __init__(self):
        self._by_hash = {}

    def mint(self, owner, tier, scopes, expires_at=None):
        """Create a key and return (raw_key, ApiKey). The raw key is shown once."""
        key_id = "key_%s" % secrets.token_hex(4)
        raw = "sk-%s-%s" % (tier, secrets.token_hex(12))
        record = ApiKey(key_id, owner, tier, scopes, expires_at)
        record.key_hash = hash_key(raw)
        self._by_hash[record.key_hash] = record
        return raw, record

    def add_seeded(self, raw_key, owner, tier, scopes, expires_at=None):
        """Register a known key (demos/tests only). Returns the ApiKey."""
        record = ApiKey("key_seed_%s" % owner, owner, tier, scopes, expires_at)
        record.key_hash = hash_key(raw_key)
        self._by_hash[record.key_hash] = record
        return record

    def verify(self, raw_key, scope, now=None):
        """Return (ApiKey or None, reason). Reason is 'ok' or an error string."""
        if not raw_key:
            return None, "missing_key"
        record = self._by_hash.get(hash_key(raw_key))
        if record is None:
            return None, "unknown_key"
        if not record.is_usable(now):
            return None, "revoked_or_expired"
        if not record.has_scope(scope):
            return None, "insufficient_scope"
        return record, "ok"

    def revoke(self, raw_key):
        record = self._by_hash.get(hash_key(raw_key))
        if record is None:
            return False
        record.revoked = True
        return True
