"""Tests for prompt-injection battery and fairness slices."""
from genai_validation.adversarial import INJECTIONS, prompt_injection
from genai_validation.candidate import CandidateModel
from genai_validation.data import CASES
from genai_validation.fairness import fairness

MODEL = CandidateModel()


def test_four_injection_probes_defined():
    ids = [p["id"] for p in INJECTIONS]
    assert ids == ["direct-override", "system-impersonation",
                   "rag-poisoned-doc", "jailbreak-roleplay"]


def test_direct_override_compromises_every_case():
    result = prompt_injection(MODEL, CASES, injections=[INJECTIONS[0]])
    assert result["attempts"] == len(CASES)
    assert result["compromised"] == sum(
        1 for c in CASES if MODEL.generate(c)["decision"] != "approve"
    )
    assert result["per_probe"][0]["success_rate"] > 0.0


def test_rag_poisoned_doc_is_resisted():
    result = prompt_injection(MODEL, CASES, injections=[INJECTIONS[2]])
    assert result["compromised"] == 0
    assert result["success_rate"] == 0.0


def test_jailbreak_roleplay_is_resisted():
    result = prompt_injection(MODEL, CASES, injections=[INJECTIONS[3]])
    assert result["compromised"] == 0


def test_injection_success_rate_is_a_fraction():
    result = prompt_injection(MODEL, CASES)
    assert result["probes"] == 4
    assert result["attempts"] == 4 * len(CASES)
    assert 0.0 < result["success_rate"] < 1.0


def test_fairness_groups_cover_all_cases():
    result = fairness(MODEL, CASES)
    assert set(result["groups"]) == {"cohort-a", "cohort-b"}
    assert sum(g["cases"] for g in result["groups"].values()) == len(CASES)
    assert result["groups"]["cohort-a"]["cases"] == 6
    assert result["groups"]["cohort-b"]["cases"] == 6


def test_fairness_rates_match_case_truth():
    result = fairness(MODEL, CASES)
    # Model matches the reference rule exactly, so approve rates follow truth.
    assert result["groups"]["cohort-a"]["approve_rate"] == 0.5
    assert result["groups"]["cohort-b"]["approve_rate"] == 0.3333
    assert result["disparate_impact_ratio"] == 0.6666


def test_fairness_equal_opportunity_gap():
    result = fairness(MODEL, CASES)
    # True-positive rate is 1.0 in both cohorts: every true approve is approved.
    assert result["equal_opportunity_gap"] == 0.0


def test_fairness_empty_cases_is_safe():
    result = fairness(MODEL, [])
    assert result["groups"] == {}
    assert result["disparate_impact_ratio"] == 1.0
    assert result["equal_opportunity_gap"] == 0.0
