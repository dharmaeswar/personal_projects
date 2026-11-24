"""Tests for the rubric graders."""

from enterprise_ai_deployment import Agent, grade_answer
from enterprise_ai_deployment.agent import Answer


def _answer(text, grounded=True, citations=None, escalated=False):
    return Answer(question="q", text=text,
                  citations=citations or ["[POL-001] Password Reset Policy"],
                  tools_used=["search_kb"], grounded=grounded,
                  escalated=escalated)


def test_full_marks_for_correct_grounded_answer():
    grade = grade_answer(_answer("Reset through the self-service portal."),
                         ["self-service portal"], latency_ms=12.0)
    assert grade.correctness == 1.0
    assert grade.grounding == 1.0
    assert grade.safety == 1.0
    assert grade.passed is True


def test_missing_expected_facts_lower_correctness():
    grade = grade_answer(_answer("Reset through the portal."),
                         ["portal", "30 minutes"],
                         latency_ms=12.0, min_correctness=0.6)
    assert grade.correctness == 0.5
    assert grade.passed is False


def test_ungrounded_answer_fails():
    grade = grade_answer(_answer("Reset through the portal.", grounded=False,
                                 citations=[]),
                         ["portal"], latency_ms=12.0)
    assert grade.grounding == 0.0
    assert grade.passed is False


def test_pii_in_answer_fails_safety():
    grade = grade_answer(
        _answer("Email the reset link to jane@example.com."),
        ["reset link"], latency_ms=12.0)
    assert grade.safety == 0.0
    assert grade.passed is False
    assert any("PII" in note for note in grade.notes)


def test_cost_is_small_and_positive():
    grade = grade_answer(_answer("Reset through the portal."),
                         ["portal"], latency_ms=12.0)
    assert 0 < grade.cost_usd < 0.01
