"""Tests for the LLM-as-judge grader."""

import pytest

from support_quality import CASES, RuleBasedJudge


def _case(case_id):
    return next(c for c in CASES if c.case_id == case_id)


def test_good_case_passes_with_high_scores():
    result = RuleBasedJudge("v1").grade(_case("case-001"))
    assert result.passed
    assert result.overall == 2.0
    assert all(score == 2 for score in result.scores.values())


def test_cash_refund_case_fails_policy():
    result = RuleBasedJudge("v1").grade(_case("case-002"))
    assert not result.passed
    assert result.scores["policy_compliance"] == 0
    assert "cash" in result.evidence["policy_compliance"]


def test_late_resolution_request_fails_policy():
    result = RuleBasedJudge("v1").grade(_case("case-005"))
    assert result.scores["policy_compliance"] == 0
    assert result.scores["accuracy"] == 0


def test_jargon_answer_fails_clarity():
    result = RuleBasedJudge("v1").grade(_case("case-008"))
    assert result.scores["clarity"] == 0
    assert "jargon" in result.evidence["clarity"]


def test_every_score_has_evidence():
    for case in CASES:
        result = RuleBasedJudge("v1").grade(case)
        assert set(result.scores) == {"accuracy", "empathy",
                                      "policy_compliance", "resolution",
                                      "clarity"}
        assert all(result.evidence[k] for k in result.scores)


def test_unknown_prompt_version_rejected():
    with pytest.raises(ValueError):
        RuleBasedJudge("v3")


def test_weakest_lists_worst_criterion_first():
    result = RuleBasedJudge("v1").grade(_case("case-002"))
    assert result.weakest()[0] in ("accuracy", "policy_compliance",
                                   "resolution")
