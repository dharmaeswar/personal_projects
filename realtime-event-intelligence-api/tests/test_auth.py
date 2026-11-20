import time

import pytest

from event_intel.auth import AuthError, TokenStore, bearer_from_header


def test_mint_and_validate_with_scope():
    tokens = TokenStore()
    token = tokens.mint_token(["alerts:read", "events:write"])
    tokens.validate(token, "alerts:read")
    tokens.validate(token, "events:write")


def test_unknown_token_rejected():
    tokens = TokenStore()
    with pytest.raises(AuthError):
        tokens.validate("no-such-token", "alerts:read")


def test_missing_token_rejected():
    tokens = TokenStore()
    with pytest.raises(AuthError):
        tokens.validate(None, "alerts:read")


def test_wrong_scope_rejected():
    tokens = TokenStore()
    token = tokens.mint_token(["alerts:read"])
    with pytest.raises(AuthError):
        tokens.validate(token, "events:write")


def test_expired_token_rejected():
    tokens = TokenStore()
    token = tokens.mint_token(["alerts:read"], ttl_seconds=1)
    # force expiry by moving the stored expiry into the past
    tokens._tokens[token]["expires_at"] = time.time() - 1
    with pytest.raises(AuthError):
        tokens.validate(token, "alerts:read")


def test_unknown_scope_rejected_at_mint():
    tokens = TokenStore()
    with pytest.raises(ValueError):
        tokens.mint_token(["admin:all"])


def test_bearer_header_parsing():
    assert bearer_from_header("Bearer abc123") == "abc123"
    assert bearer_from_header("bearer abc123") == "abc123"
    assert bearer_from_header("Basic abc123") is None
    assert bearer_from_header(None) is None
    assert bearer_from_header("") is None
