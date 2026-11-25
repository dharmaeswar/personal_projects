"""Tests for versioned API contracts and backward compatibility."""

import pytest

from event_intel.apiversion import (ApiContract, check_backward_compat,
                                    deprecate, negotiate_version)

V1 = ApiContract("v1", {"id": "string", "score": "number",
                        "source_id": "string"})
V2_ADDITIVE = ApiContract("v2", {"id": "string", "score": "number",
                                 "source_id": "string",
                                 "severity": "string"})
V2_REMOVED = ApiContract("v2", {"id": "string", "score": "number"})
V2_RETYPED = ApiContract("v2", {"id": "string", "score": "string",
                                "source_id": "string"})


def test_additive_change_is_compatible():
    result = check_backward_compat(V1, V2_ADDITIVE)
    assert result["compatible"] is True
    assert result["violations"] == []
    assert result["added_fields"] == ["severity"]


def test_removed_field_is_violation():
    result = check_backward_compat(V1, V2_REMOVED)
    assert result["compatible"] is False
    assert result["violations"] == ["field removed: source_id"]


def test_retyped_field_is_violation():
    result = check_backward_compat(V1, V2_RETYPED)
    assert result["compatible"] is False
    assert any("field type changed: score" in v
               for v in result["violations"])


def test_negotiate_picks_highest_supported_below_request():
    assert negotiate_version("v3", ["v1", "v2"]) == "v2"
    assert negotiate_version("v2", ["v1", "v2"]) == "v2"
    assert negotiate_version("v1", ["v1", "v2"]) == "v1"


def test_negotiate_rejects_too_old_client():
    with pytest.raises(ValueError):
        negotiate_version("v1", ["v2", "v3"])


def test_deprecate_records_removal_version():
    updated = deprecate(V1, "source_id", "v3")
    assert updated.deprecated == {"source_id": "v3"}
    assert updated.fields == V1.fields  # field stays usable


def test_deprecate_unknown_field_rejected():
    with pytest.raises(ValueError):
        deprecate(V1, "nope", "v3")
