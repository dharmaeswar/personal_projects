"""Tests for masking policies."""

from governance.masking import (
    deterministic_hash,
    mask_value,
    partial_mask,
    redact,
    tokenize,
)


def test_redact():
    assert redact("jordan.lee@example.com") == "[REDACTED]"
    assert redact(12345) == "[REDACTED]"


def test_partial_mask_shows_last_four():
    value = "jordan.lee@example.com"
    assert partial_mask(value) == "*" * (len(value) - 4) + value[-4:]
    assert partial_mask("987-65-4321") == "*******4321"


def test_partial_mask_short_value_fully_masked():
    assert partial_mask("abc") == "***"
    assert partial_mask("") == ""


def test_deterministic_hash_is_stable_and_hex():
    h1 = deterministic_hash("987-65-4321")
    h2 = deterministic_hash("987-65-4321")
    assert h1 == h2
    assert len(h1) == 64
    assert all(ch in "0123456789abcdef" for ch in h1)


def test_deterministic_hash_differs_by_value_and_salt():
    assert deterministic_hash("a") != deterministic_hash("b")
    assert deterministic_hash("a") != deterministic_hash("a", salt="other-salt")


def test_tokenize_is_stable_within_a_map():
    mapping = {}
    t1 = tokenize("jordan.lee@example.com", mapping)
    t2 = tokenize("jordan.lee@example.com", mapping)
    assert t1 == t2
    assert t1.startswith("TOK-")
    assert tokenize("other@example.com", mapping) != t1


def test_mask_value_public_and_internal_unchanged():
    assert mask_value("x", "public", "analyst") == "x"
    assert mask_value("x", "internal", "analyst") == "x"


def test_mask_value_confidential_partial_for_analyst():
    value = "jordan.lee@example.com"
    assert mask_value(value, "confidential", "analyst") == \
        "*" * (len(value) - 4) + value[-4:]


def test_mask_value_confidential_raw_for_admin():
    assert mask_value("jordan.lee@example.com", "confidential", "admin") == \
        "jordan.lee@example.com"


def test_mask_value_restricted_never_raw_for_non_privileged():
    raw = "987-65-4321"
    for role in ("analyst", "auditor"):
        masked = mask_value(raw, "restricted", role)
        assert masked != raw
        assert masked == deterministic_hash(raw)


def test_mask_value_restricted_raw_for_privileged():
    assert mask_value("987-65-4321", "restricted", "data-engineer") == "987-65-4321"
    assert mask_value("987-65-4321", "restricted", "admin") == "987-65-4321"
