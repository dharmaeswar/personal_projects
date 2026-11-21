import time

from gateway.auth import KeyStore, hash_key


def test_mint_and_verify_ok():
    store = KeyStore()
    raw, record = store.mint("acme", "pro", ("models:invoke", "usage:read"))
    assert record.key_hash == hash_key(raw)
    found, reason = store.verify(raw, "models:invoke")
    assert reason == "ok" and found.key_id == record.key_id


def test_unknown_key_rejected():
    store = KeyStore()
    _, reason = store.verify("sk-nope", "models:invoke")
    assert reason == "unknown_key"


def test_missing_key_rejected():
    store = KeyStore()
    _, reason = store.verify("", "models:invoke")
    assert reason == "missing_key"


def test_wrong_scope_rejected():
    store = KeyStore()
    raw, _ = store.mint("acme", "pro", ("usage:read",))
    _, reason = store.verify(raw, "models:invoke")
    assert reason == "insufficient_scope"


def test_expired_key_rejected():
    store = KeyStore()
    raw, _ = store.mint("acme", "pro", ("models:invoke",), expires_at=time.time() - 10)
    _, reason = store.verify(raw, "models:invoke")
    assert reason == "revoked_or_expired"


def test_revoked_key_rejected():
    store = KeyStore()
    raw, _ = store.mint("acme", "pro", ("models:invoke",))
    assert store.revoke(raw) is True
    _, reason = store.verify(raw, "models:invoke")
    assert reason == "revoked_or_expired"


def test_invalid_tier_rejected():
    store = KeyStore()
    try:
        store.mint("acme", "ultra", ("models:invoke",))
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown tier")
