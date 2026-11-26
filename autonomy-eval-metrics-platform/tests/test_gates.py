from eval_platform.compare import compare_rates
from eval_platform.gates import Gate, build_release_evidence


def _comp(verdict="improvement", delta=-0.002, value=0.008):
    return type("C", (), {"verdict": verdict, "delta": delta,
                          "candidate_value": value, "reason": "test"})()


def test_gate_blocks_inconclusive_comparison():
    gate = Gate("intervention_rate", max_regression=0.005, higher_is_better=False)
    ok, msg = gate.evaluate(_comp(verdict="inconclusive", delta=0.002, value=0.012))
    assert ok is False and "BLOCKED" in msg  # inconclusive blocks the gate


def test_gate_fails_regression_beyond_tolerance():
    gate = Gate("intervention_rate", max_regression=0.005, higher_is_better=False)
    c = compare_rates(10, 1000, 40, 1000, "intervention_rate", False)
    assert c.verdict == "regression"
    ok, msg = gate.evaluate(c)
    assert ok is False and "FAIL" in msg


def test_gate_fails_below_floor():
    gate = Gate("mission_completion", min_value=0.95, higher_is_better=True)
    c = compare_rates(900, 1000, 800, 1000, "mission_completion", True)
    ok, msg = gate.evaluate(c)
    assert ok is False and "below floor" in msg


def test_gate_passes_improvement():
    gate = Gate("mission_completion", min_value=0.95, higher_is_better=True)
    c = compare_rates(900, 1000, 960, 1000, "mission_completion", True)
    ok, _ = gate.evaluate(c)
    assert ok is True


def test_release_evidence_summary():
    gates = [Gate("mission_completion", min_value=0.95, higher_is_better=True)]
    comparisons = {"mission_completion": compare_rates(900, 1000, 960, 1000,
                                                       "mission_completion", True)}
    evidence = build_release_evidence("model-2026.11", gates, comparisons)
    assert evidence.passed is True
    assert evidence.summary()["release_ready"] is True
    assert evidence.summary()["gates_passed"] == 1


def test_missing_comparison_blocks_release():
    evidence = build_release_evidence("m1", [Gate("x", min_value=0.9)], {})
    assert evidence.passed is False
    assert "BLOCKED" in evidence.summary()["details"][0]
