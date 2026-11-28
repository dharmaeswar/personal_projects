"""Tests for graders and token-level parity checks."""

from interaction_lib import (
    ToolCall,
    check_token_parity,
    grade_exact_match,
    grade_json_validity,
    grade_tool_call,
)


def test_exact_match_ignores_case_and_whitespace():
    assert grade_exact_match("  The Answer ", "the answer").score == 1.0
    assert grade_exact_match("42", "43").score == 0.0


def test_json_validity():
    assert grade_json_validity('{"a": 1}').score == 1.0
    assert grade_json_validity('{"a": }').score == 0.0
    assert grade_json_validity('[1, 2]').score == 0.0


def test_tool_call_grade_full_match():
    call = ToolCall("add", {"a": 2, "b": 3}, "")
    assert grade_tool_call(call, "add", {"a": 2, "b": 3}).score == 1.0


def test_tool_call_grade_wrong_tool_scores_zero():
    call = ToolCall("subtract", {"a": 2, "b": 3}, "")
    assert grade_tool_call(call, "add", {"a": 2, "b": 3}).score == 0.0


def test_tool_call_grade_partial_arguments():
    call = ToolCall("add", {"a": 2, "b": 9}, "")
    result = grade_tool_call(call, "add", {"a": 2, "b": 3})
    assert result.score == 0.75
    assert "b" in result.reason


def test_parity_match():
    from interaction_lib import SimpleTokenizer

    tok = SimpleTokenizer()
    result = check_token_parity("Hello, world!", lambda text: tok.tokenize(text))
    assert result.matched is True
    assert result.first_mismatch is None


def test_parity_mismatch_reports_index():
    result = check_token_parity("Hello, world!", lambda text: ["Hello", ",", "World", "!"])
    assert result.matched is False
    assert result.first_mismatch == 2
