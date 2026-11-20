"""Tests for the evaluation harness and release gates."""

import json

from edu_ai_evaluation_guardrails.data import load_cases
from edu_ai_evaluation_guardrails.gates import GateThresholds, evaluate_gate
from edu_ai_evaluation_guardrails.harness import run_evaluation


def test_harness_redacts_pii_before_grading(tmp_path):
    log = tmp_path / "run.jsonl"
    cases = [c for c in load_cases() if c["case_id"] == "privacy-01"]
    results, summary = run_evaluation(cases, known_names=("Maya Chen",),
                                      log_path=str(log))
    assert len(results) == 1
    assert summary.total_redactions >= 3  # name, email, student id
    assert summary.pii_leaks == 0
    # The log must not contain the raw PII anywhere.
    content = log.read_text()
    assert "maya.chen@example.edu" not in content
    assert "482913" not in content
    assert "Maya Chen" not in content


def test_harness_summary_and_log(tmp_path):
    log = tmp_path / "run.jsonl"
    _, summary = run_evaluation(load_cases(), log_path=str(log))
    assert summary.cases == 8
    assert 0.0 <= summary.mean_overall <= 1.0
    assert summary.safety_failures == 0
    assert summary.pii_leaks == 0
    assert set(summary.per_subject) == {"algebra", "biology", "history",
                                         "privacy", "safety"}
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(records) == 9  # 8 cases + 1 summary
    assert records[-1]["type"] == "summary"
    assert records[-1]["cases"] == 8


def test_harness_without_log_path():
    _, summary = run_evaluation(load_cases())
    assert summary.cases == 8


def test_gate_passes_on_good_summary():
    decision = evaluate_gate({
        "mean_overall": 0.9, "mean_correctness": 0.85,
        "safety_failures": 0, "pii_leaks": 0})
    assert decision.passed
    assert decision.reasons == []


def test_gate_fails_on_low_scores_and_leaks():
    decision = evaluate_gate({
        "mean_overall": 0.5, "mean_correctness": 0.6,
        "safety_failures": 1, "pii_leaks": 2})
    assert not decision.passed
    assert len(decision.reasons) == 4


def test_gate_custom_thresholds():
    decision = evaluate_gate(
        {"mean_overall": 0.8, "mean_correctness": 0.75,
         "safety_failures": 0, "pii_leaks": 0},
        GateThresholds(min_mean_overall=0.9, min_mean_correctness=0.7))
    assert not decision.passed
    assert any("overall" in r for r in decision.reasons)


def test_synthetic_data_has_expected_cases():
    cases = load_cases()
    assert len(cases) == 8
    assert all({"case_id", "subject", "prompt", "response",
                "expected_points"} <= set(c) for c in cases)
