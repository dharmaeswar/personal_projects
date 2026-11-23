import time

import pytest

from gateway import TokenStore


@pytest.fixture
def store():
    return TokenStore(secret=b"test-secret")


def test_issue_and_verify_round_trip(store):
    token = store.issue("agent-1", "deployer", ["deploy:service:web"], "prod")
    rec = store.verify(token)
    assert rec.agent == "agent-1"
    assert rec.role == "deployer"
    assert rec.scopes == ["deploy:service:web"]
    assert rec.environment == "prod"


def test_scopes_are_deduplicated_and_sorted(store):
    token = store.issue("a", "deployer", ["read:x", "deploy:y", "read:x"], "prod")
    assert store.verify(token).scopes == ["deploy:y", "read:x"]


def test_expired_token_rejected(store):
    token = store.issue("a", "deployer", ["read:x"], "prod",
                        ttl_seconds=60, now=1000.0)
    with pytest.raises(ValueError, match="expired"):
        store.verify(token, now=2000.0)


def test_token_valid_before_expiry(store):
    token = store.issue("a", "deployer", ["read:x"], "prod",
                        ttl_seconds=60, now=1000.0)
    assert store.verify(token, now=1059.0).agent == "a"


def test_revoked_token_rejected(store):
    token = store.issue("a", "deployer", ["read:x"], "prod")
    assert store.revoke(store.token_id(token)) is True
    with pytest.raises(ValueError, match="revoked"):
        store.verify(token)


def test_revoke_unknown_id_returns_false(store):
    assert store.revoke("no-such-id") is False


def test_tampered_payload_rejected(store):
    token = store.issue("a", "deployer", ["read:x"], "prod")
    raw, sig = token.split(".")
    tampered = raw[:-2] + "AA" + "." + sig
    with pytest.raises(ValueError, match="signature"):
        store.verify(tampered)


def test_malformed_token_rejected(store):
    with pytest.raises(ValueError, match="malformed"):
        store.verify("not-a-token")


def test_token_from_other_secret_rejected(store):
    other = TokenStore(secret=b"different-secret")
    token = other.issue("a", "deployer", ["read:x"], "prod")
    with pytest.raises(ValueError, match="signature"):
        store.verify(token)
