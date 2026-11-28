"""Tests for tool-call parsing and validation."""

from interaction_lib import ToolCall, ToolSpec, parse_tool_calls, validate_tool_call


def _specs():
    return {
        "add": ToolSpec("add", parameters={"a": "integer", "b": "integer"}, required=("a", "b")),
        "search": ToolSpec("search", parameters={"query": "string"}, required=("query",)),
    }


def test_parse_fenced_json_block():
    text = 'Here you go:\n```json\n{"name": "add", "arguments": {"a": 2, "b": 3}}\n```'
    calls = parse_tool_calls(text)
    assert calls == [ToolCall("add", {"a": 2, "b": 3}, '{"name": "add", "arguments": {"a": 2, "b": 3}}')]


def test_parse_tool_call_tag():
    text = '<tool_call>{"name": "search", "arguments": {"query": "cats"}}</tool_call>'
    calls = parse_tool_calls(text)
    assert len(calls) == 1 and calls[0].name == "search"


def test_non_tool_json_is_skipped():
    assert parse_tool_calls('```json\n{"answer": 42}\n```') == []


def test_malformed_json_is_skipped():
    assert parse_tool_calls('```json\n{not json\n```') == []


def test_valid_call_has_no_errors():
    call = ToolCall("add", {"a": 2, "b": 3}, "")
    assert validate_tool_call(call, _specs()) == []


def test_unknown_tool_reported():
    call = ToolCall("divide", {"a": 2, "b": 3}, "")
    assert validate_tool_call(call, _specs()) == ["unknown tool 'divide'"]


def test_missing_required_parameter_reported():
    call = ToolCall("add", {"a": 2}, "")
    assert validate_tool_call(call, _specs()) == ["missing required parameter 'b'"]


def test_wrong_argument_type_reported():
    call = ToolCall("add", {"a": "two", "b": 3}, "")
    errors = validate_tool_call(call, _specs())
    assert errors == ["parameter 'a' must be integer, got str"]


def test_bool_is_not_an_integer():
    call = ToolCall("add", {"a": True, "b": 3}, "")
    errors = validate_tool_call(call, _specs())
    assert errors == ["parameter 'a' must be integer, got bool"]


def test_spec_rejects_undeclared_required_param():
    import pytest

    with pytest.raises(ValueError):
        ToolSpec("add", parameters={"a": "integer"}, required=("a", "b"))
