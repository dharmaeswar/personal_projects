"""Tests: contracts, validation, error semantics, partial success."""

import pytest

from integration_surface.contracts import (
    ContractError,
    PartialSuccess,
    ToolError,
    ToolResult,
    validate_call,
)


def test_validate_missing_required():
    with pytest.raises(ContractError, match="missing required field: schema"):
        validate_call({}, {"required": ["schema"], "properties": {"schema": {"type": "string"}}})


def test_validate_wrong_type():
    with pytest.raises(ContractError, match="expected integer"):
        validate_call({"n": "3"}, {"properties": {"n": {"type": "integer"}}})


def test_validate_unknown_field_rejected():
    with pytest.raises(ContractError, match="unknown field"):
        validate_call({"a": 1, "zzz": 2}, {"properties": {"a": {"type": "integer"}}})


def test_validate_enum_and_bounds():
    schema = {"properties": {
        "mode": {"type": "string", "enum": ["dry_run", "full"]},
        "n": {"type": "integer", "minimum": 0, "maximum": 5},
        "tags": {"type": "array", "minItems": 1},
    }}
    validate_call({"mode": "dry_run", "n": 3, "tags": ["x"]}, schema)
    with pytest.raises(ContractError, match="not in"):
        validate_call({"mode": "live"}, schema)
    with pytest.raises(ContractError, match="below minimum"):
        validate_call({"n": -1}, schema)
    with pytest.raises(ContractError, match="above maximum"):
        validate_call({"n": 9}, schema)
    with pytest.raises(ContractError, match="at least 1 items"):
        validate_call({"tags": []}, schema)


def test_validate_nested_object():
    schema = {"properties": {"cfg": {"type": "object", "required": ["k"],
                                     "properties": {"k": {"type": "string"}}}}}
    with pytest.raises(ContractError, match="missing required field: k"):
        validate_call({"cfg": {}}, schema)


def test_partial_success_mixed():
    p = PartialSuccess()
    p.record("a", True, {"rows": 10})
    p.record("b", False, error="not_found: b")
    result = p.as_result()
    assert result.partial is True
    assert result.ok is False
    assert result.error.code == "partial_success"
    assert result.to_dict()["partial_success"] is True


def test_partial_success_all_ok():
    p = PartialSuccess()
    p.record("a", True)
    assert p.as_result().ok is True


def test_partial_success_all_failed():
    p = PartialSuccess()
    p.record("a", False, error="boom")
    result = p.as_result()
    assert result.ok is False
    assert result.error.code == "batch_failed"


def test_tool_result_to_dict_error_shape():
    r = ToolResult(ok=False, error=ToolError("forbidden", "no scope"))
    d = r.to_dict()
    assert d == {"ok": False, "error": {"code": "forbidden", "message": "no scope"}}
