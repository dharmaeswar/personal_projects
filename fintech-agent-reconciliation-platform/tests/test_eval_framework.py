from fintech_agents.eval_framework import (
    EvaluationFramework, GoldenCase, rubric_judge)


def _case():
    return GoldenCase(
        "close-nov",
        source_numbers={"total": 8_430_000, "arr": 11_500_000},
        expected_numbers={"total": 8_430_000, "arr": 11_500_000},
        expected_fields=["close report"])


def test_judge_passes_exact_grounded_answer():
    result = rubric_judge(
        _case(), {"total": 8_430_000, "arr": 11_500_000},
        "close report: totals check out")
    assert result["passed"] is True
    assert result["score"] == 1.0
    assert result["ungrounded_fields"] == []


def test_judge_fails_wrong_number():
    result = rubric_judge(
        _case(), {"total": 9_999_999, "arr": 11_500_000},
        "close report")
    assert result["passed"] is False
    assert result["checks"]["accuracy"] == 0.5


def test_judge_flags_ungrounded_number():
    result = rubric_judge(
        _case(), {"total": 8_430_000, "arr": 11_500_000,
                  "invented": 42},
        "close report")
    assert result["passed"] is False
    assert result["ungrounded_fields"] == ["invented"]
    assert result["checks"]["grounding"] == 0.0


def test_judge_marks_missing_field_incomplete():
    result = rubric_judge(
        _case(), {"total": 8_430_000, "arr": 11_500_000},
        "totals only, no report label")
    assert result["checks"]["completeness"] == 0.0


def test_framework_reports_missing_answer():
    fw = EvaluationFramework([_case()])
    result = fw.evaluate({})
    assert result["cases"] == 1
    assert result["passed"] == 0
    assert result["overall_passed"] is False
    assert result["per_case"]["close-nov"]["reason"] == \
        "no answer supplied"


def test_framework_overall_pass():
    fw = EvaluationFramework([_case()])
    result = fw.evaluate({"close-nov": {
        "numbers": {"total": 8_430_000, "arr": 11_500_000},
        "text": "close report"}})
    assert result["overall_passed"] is True


def test_regression_gate_catches_score_drop():
    fw = EvaluationFramework([_case()])
    fw.set_baseline({"close-nov": 1.0})
    gate = fw.regression_gate({"close-nov": 0.75})
    assert gate["passed"] is False
    assert gate["regressions"]["close-nov"] == (1.0, 0.75)


def test_regression_gate_passes_when_scores_hold():
    fw = EvaluationFramework([_case()])
    fw.set_baseline({"close-nov": 0.8})
    assert fw.regression_gate({"close-nov": 0.9})["passed"] is True
    # Cases with no baseline are skipped, not failed.
    assert fw.regression_gate({"other": 0.1})["passed"] is True
