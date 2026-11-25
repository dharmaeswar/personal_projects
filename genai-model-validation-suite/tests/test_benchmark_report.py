"""Tests for benchmarking and the SR 26-2-style validation report."""
from genai_validation.benchmark import accuracy, benchmark
from genai_validation.candidate import BenchmarkModel, CandidateModel, ChallengerModel
from genai_validation.data import CASES
from genai_validation.harness import run_validation

CANDIDATE = CandidateModel()
CHALLENGER = ChallengerModel()


def test_challenger_matches_ground_truth():
    result = accuracy(CHALLENGER, CASES)
    assert result["accuracy"] == 1.0
    assert result["correct"] == len(CASES)


def test_candidate_seed_zero_matches_ground_truth():
    result = accuracy(CANDIDATE, CASES, seed=0)
    assert result["accuracy"] == 1.0


def test_benchmark_is_base_rate_only():
    model = BenchmarkModel(CASES)
    result = accuracy(model, CASES)
    assert result["accuracy"] == round(5 / 12, 4)  # "approve" is the majority truth


def test_benchmark_comparison_shape():
    result = benchmark(CANDIDATE, CHALLENGER, BenchmarkModel(CASES), CASES)
    assert result["champion_minus_challenger"] == 0.0
    assert result["champion_beats_benchmark"] is True


def test_full_run_fails_gates_because_of_seeded_faults():
    results = run_validation()
    assert results["cases"] == len(CASES)
    assert results["report"]["verdict"] == "FAIL"
    assert results["report"]["findings"]
    assert "F-02" in {f["id"] for f in results["report"]["findings"]}


def test_full_run_reports_all_sections():
    results = run_validation()
    for key in ("hallucination", "benchmark", "reliability",
                "sensitivity", "drift", "explainability",
                "prompt_injection", "fairness", "report"):
        assert key in results
    assert results["hallucination"]["rate"] == 0.0  # clean seed-0 run
    assert results["sensitivity"]["flip_rate"] == 0.0
    assert results["explainability"]["mean_coverage"] == 1.0
    assert results["prompt_injection"]["success_rate"] == 0.2917
    assert results["fairness"]["disparate_impact_ratio"] == 0.6666
    assert set(results["report"]["gates"]) == {
        "hallucination_rate", "decision_agreement", "sensitivity",
        "drift", "explainability", "benchmark",
        "prompt_injection", "fairness"}
