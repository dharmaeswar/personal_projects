"""Tests for the eval harness, regression reports and release gates."""

import pytest

from agent_eval.agent import AnalyticsAgent
from agent_eval.evals import (FAILURE_HANDLING_CASE, TASK_SET_V1,
                              grade_groundedness, run_eval_set)
from agent_eval.regression import (compare_to_baseline, release_gate)
from agent_eval.sandbox import Sandbox
from agent_eval.tools import ToolServer


@pytest.fixture
def setup():
    sandbox = Sandbox()
    agent = AnalyticsAgent(ToolServer(sandbox))
    return agent, sandbox


def test_task_set_has_eight_scored_cases():
    assert len(TASK_SET_V1) == 8
    assert len({c["id"] for c in TASK_SET_V1}) == 8
    assert sum(1 for c in TASK_SET_V1 if c["human_reviewed"]) == 6


def test_full_eval_set_passes(setup):
    agent, sandbox = setup
    results = run_eval_set(agent, sandbox)
    assert results["pass_count"] == results["total"] == 8
    assert results["pass_rate"] == 1.0
    assert results["failure_modes"] == {}


def test_failure_handling_case_declines_to_answer(setup):
    agent, sandbox = setup
    results = run_eval_set(agent, sandbox)
    fh = results["failure_handling"]
    assert fh["id"] == FAILURE_HANDLING_CASE["id"]
    assert fh["passed"] is True


def test_groundedness_grader_catches_invented_number():
    graded = grade_groundedness(
        "The answer is 99999 (avg_score).", [[187.5]], "What is the average?")
    assert graded["grounded"] is False
    assert "99999" in graded["missing_numbers"]


def test_groundedness_grader_accepts_true_summary():
    graded = grade_groundedness(
        "The answer is 187.5 (avg_score).", [[187.5]], "What is the average?")
    assert graded["grounded"] is True


def test_release_gate_passes_on_clean_run(setup):
    agent, sandbox = setup
    results = run_eval_set(agent, sandbox)
    gate = release_gate(results, None)
    assert gate["gate"] == "PASS"
    assert gate["reasons"] == []


def test_release_gate_blocks_low_pass_rate():
    results = {
        "pass_rate": 0.5,
        "cases": [{"id": "a", "human_reviewed": True, "passed": False}],
        "failure_handling": {"passed": True},
    }
    gate = release_gate(results, None)
    assert gate["gate"] == "BLOCKED"
    assert any("pass rate" in r for r in gate["reasons"])


def test_regression_detects_newly_failing_case():
    baseline = {"cases": [{"id": "a", "passed": True,
                           "latency_ms": 10, "cost_usd": 0.01}]}
    fresh = {"cases": [{"id": "a", "passed": False,
                        "latency_ms": 10, "cost_usd": 0.01}]}
    compared = compare_to_baseline(fresh, baseline)
    assert compared["regressions"] == ["newly failing case: a"]


def test_regression_detects_cost_growth_over_threshold():
    baseline = {"cases": [{"id": "a", "passed": True,
                           "latency_ms": 10, "cost_usd": 0.01}]}
    fresh = {"cases": [{"id": "a", "passed": True,
                        "latency_ms": 10, "cost_usd": 0.02}]}
    compared = compare_to_baseline(fresh, baseline)
    assert any("cost_usd grew" in r for r in compared["regressions"])
