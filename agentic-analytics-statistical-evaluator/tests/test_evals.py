"""Tests for the agentic evals module (LLM-judge trajectory scoring).

The judge is rule-based and deterministic, so expected verdicts are
exact: a clean trajectory must pass, and each known-bad mutation must
fail on the criterion it breaks.
"""

from agentic_stats import evals


def _good():
    return evals._good_trajectory()


def test_good_trajectory_passes():
    judged = evals.judge_trajectory(_good())
    assert judged["verdict"] == "PASS"
    assert judged["overall"] >= 0.70
    assert all(0.0 <= s <= 1.0 for s in judged["scores"].values())


def test_good_trajectory_scores_high_on_every_criterion():
    judged = evals.judge_trajectory(_good())
    assert judged["scores"]["grounding"] >= 0.5
    assert judged["scores"]["tool_use"] == 1.0
    assert judged["scores"]["coherence"] == 1.0
    assert judged["scores"]["reasoning"] >= 0.5


def test_hallucinated_claim_fails_coherence():
    judged = evals.judge_trajectory(evals._mutate(_good(), "hallucinated-claim"))
    assert judged["verdict"] == "FAIL"
    # The invented "99" is in no tool result, so coherence drops.
    assert judged["scores"]["coherence"] < 1.0


def test_bad_tool_fails_tool_use():
    judged = evals.judge_trajectory(evals._mutate(_good(), "bad-tool"))
    assert judged["verdict"] == "FAIL"
    assert judged["scores"]["tool_use"] < 1.0


def test_missing_result_fails_tool_use():
    judged = evals.judge_trajectory(evals._mutate(_good(), "missing-result"))
    assert judged["verdict"] == "FAIL"
    assert judged["scores"]["tool_use"] < 1.0


def test_unsupported_answer_fails_grounding():
    judged = evals.judge_trajectory(evals._mutate(_good(), "unsupported-answer"))
    assert judged["verdict"] == "FAIL"
    assert judged["scores"]["grounding"] == 0.0


def test_empty_trajectory_fails():
    judged = evals.judge_trajectory([])
    assert judged["verdict"] == "FAIL"
    assert judged["overall"] < 0.70


def test_answer_with_no_tool_calls_fails_tool_use():
    traj = [{"kind": "answer", "text": "There are 42 at-risk accounts."}]
    judged = evals.judge_trajectory(traj)
    assert judged["scores"]["tool_use"] == 0.0
    assert judged["verdict"] == "FAIL"


def test_synthetic_cases_are_deterministic():
    first = evals.generate_synthetic_cases(n=10, seed=11)
    second = evals.generate_synthetic_cases(n=10, seed=11)
    assert first == second


def test_synthetic_cases_cover_all_kinds():
    cases = evals.generate_synthetic_cases(n=10, seed=11)
    kinds = {c["kind"] for c in cases}
    assert kinds == {"good", "hallucinated-claim", "bad-tool",
                     "missing-result", "unsupported-answer"}
    assert sum(1 for c in cases if c["expected"] == "PASS") == 2
    assert sum(1 for c in cases if c["expected"] == "FAIL") == 8


def test_benchmark_judge_accuracy_is_high():
    bench = evals.run_benchmark(evals.generate_synthetic_cases(n=10, seed=11))
    assert bench["n"] == 10
    # The judge must agree with the known verdict on at least 9 of 10.
    assert bench["judge_accuracy"] >= 0.9
    assert bench["pass_rate"] == 0.2
    assert 0.0 <= bench["mean_overall"] <= 1.0


def test_benchmark_criterion_means_are_bounded():
    bench = evals.run_benchmark(evals.generate_synthetic_cases(n=10, seed=11))
    for value in bench["criterion_means"].values():
        assert 0.0 <= value <= 1.0


def test_no_regression_on_identical_runs():
    scores = [0.9, 0.8, 0.85, 0.9, 0.75, 0.9, 0.8, 0.85, 0.9, 0.8]
    result = evals.detect_regression(scores, scores)
    assert result["regression"] is False
    assert result["mean_diff"] == 0.0


def test_clear_drop_is_a_regression():
    baseline = [0.9, 0.88, 0.92, 0.9, 0.89, 0.91, 0.9, 0.88, 0.9, 0.91]
    current = [0.5, 0.52, 0.48, 0.51, 0.49, 0.5, 0.53, 0.47, 0.5, 0.51]
    result = evals.detect_regression(current, baseline)
    assert result["regression"] is True
    assert result["mean_diff"] < -0.3
    assert result["p_value"] < 0.05


def test_small_wobble_is_not_a_regression():
    baseline = [0.9, 0.88, 0.92, 0.9, 0.89, 0.91, 0.9, 0.88, 0.9, 0.91]
    current = [0.88, 0.87, 0.9, 0.88, 0.86, 0.89, 0.88, 0.87, 0.89, 0.88]
    result = evals.detect_regression(current, baseline)
    assert result["regression"] is False


def test_diagnose_maps_bad_tool_to_tool_fix():
    bench = evals.run_benchmark(evals.generate_synthetic_cases(n=10, seed=11))
    diagnoses = {d["id"]: d for d in evals.diagnose_failures(bench)}
    bad_tool = next(r for r in bench["results"] if r["kind"] == "bad-tool")
    assert diagnoses[bad_tool["id"]]["category"] == "tool"


def test_diagnose_maps_unsupported_answer_to_prompt_fix():
    bench = evals.run_benchmark(evals.generate_synthetic_cases(n=10, seed=11))
    diagnoses = {d["id"]: d for d in evals.diagnose_failures(bench)}
    unsupported = next(
        r for r in bench["results"] if r["kind"] == "unsupported-answer")
    assert diagnoses[unsupported["id"]]["category"] == "prompt"


def test_diagnose_skips_passing_cases():
    bench = evals.run_benchmark(evals.generate_synthetic_cases(n=10, seed=11))
    diagnosed = {d["id"] for d in evals.diagnose_failures(bench)}
    passing = {r["id"] for r in bench["results"] if r["verdict"] == "PASS"}
    assert not (diagnosed & passing)


def test_report_contains_key_lines():
    bench = evals.run_benchmark(evals.generate_synthetic_cases(n=10, seed=11))
    report = evals.render_evals_report(bench)
    assert "AGENTIC EVALS REPORT" in report
    assert "Cases judged: 10" in report
    assert "Pass rate:" in report
    assert "Judge accuracy" in report
