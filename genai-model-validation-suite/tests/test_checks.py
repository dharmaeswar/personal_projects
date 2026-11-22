"""Tests for reliability, sensitivity, drift and explainability checks."""
from genai_validation.candidate import CandidateModel
from genai_validation.checks import explainability, jaccard, psi, reliability, sensitivity
from genai_validation.data import CASES

MODEL = CandidateModel()


def test_reliability_detects_unstable_decisions():
    result = reliability(MODEL, CASES, seeds=(0, 1, 2, 3, 4))
    assert result["cases"] == len(CASES)
    assert result["unstable_cases"] >= 1
    assert result["mean_decision_agreement"] < 1.0
    assert result["mean_decision_agreement"] > 0.5


def test_reliability_clean_seeds_are_stable():
    result = reliability(MODEL, CASES, seeds=(0, 1, 2))
    assert result["mean_decision_agreement"] == 1.0
    assert result["unstable_cases"] == 0


def test_sensitivity_prompt_rewording_flips_nothing():
    result = sensitivity(MODEL, CASES)
    assert result["flip_rate"] == 0.0
    assert result["flips"] == 0


def test_psi_zero_for_identical_distributions():
    scores = [c["facts"]["utilization"] / 100 for c in CASES]
    assert psi(scores, list(scores)) == 0.0


def test_psi_positive_for_shifted_distribution():
    scores = [c["facts"]["utilization"] / 100 for c in CASES]
    shifted = [min(1.0, s + 0.25) for s in scores]
    assert psi(scores, shifted) > 0.10


def test_jaccard_identical_text_is_one():
    assert jaccard("approve utilization 24%", "approve utilization 24%") == 1.0


def test_explainability_cites_decision_drivers():
    case = CASES[0]
    out = MODEL.generate(case, seed=0)
    result = explainability(out["explanation"], case["facts"],
                            ["utilization", "months_delinquent"])
    assert result["coverage"] == 1.0
    assert set(result["cited_drivers"]) == {"utilization", "months_delinquent"}


def test_explainability_empty_explanation_scores_zero():
    result = explainability("", CASES[0]["facts"],
                            ["utilization", "months_delinquent"])
    assert result["coverage"] == 0.0
