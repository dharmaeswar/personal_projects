from agent_eval.regression import compare


def _baseline():
    return {"pass_rate": 1.0, "total": 2, "passed": 2, "cases": [
        {"case_id": "A", "passed": True, "failures": [],
         "latency_ms": 100, "cost_usd": 0.001},
        {"case_id": "B", "passed": True, "failures": [],
         "latency_ms": 200, "cost_usd": 0.002}]}


def _current(passes=(True, True), latencies=(100, 200), costs=(0.001, 0.002)):
    return {"pass_rate": sum(passes) / 2, "total": 2,
            "passed": sum(passes), "cases": [
                {"case_id": "A", "passed": passes[0], "failures": []
                 if passes[0] else ["decision wrong"],
                 "latency_ms": latencies[0], "cost_usd": costs[0]},
                {"case_id": "B", "passed": passes[1], "failures": []
                 if passes[1] else ["decision wrong"],
                 "latency_ms": latencies[1], "cost_usd": costs[1]}]}


def test_identical_run_passes():
    verdict = compare(_baseline(), _current())
    assert verdict["verdict"] == "PASS"
    assert verdict["pass_rate_delta"] == 0.0
    assert verdict["regressions"] == []


def test_newly_failing_case_is_regression():
    verdict = compare(_baseline(), _current(passes=(True, False)))
    assert verdict["verdict"] == "REGRESSION"
    assert any("B: passed in baseline, fails now" in r for r in verdict["regressions"])
    assert verdict["pass_rate_delta"] == -0.5


def test_latency_growth_beyond_tolerance_is_regression():
    verdict = compare(_baseline(), _current(latencies=(100, 260)))
    assert verdict["verdict"] == "REGRESSION"
    assert any("latency up 30.0%" in r for r in verdict["regressions"])


def test_small_latency_growth_within_tolerance_passes():
    verdict = compare(_baseline(), _current(latencies=(100, 210)))
    assert verdict["verdict"] == "PASS"


def test_cost_growth_beyond_tolerance_is_regression():
    verdict = compare(_baseline(), _current(costs=(0.001, 0.0025)))
    assert verdict["verdict"] == "REGRESSION"
    assert any("cost up 25.0%" in r for r in verdict["regressions"])


def test_missing_case_is_regression():
    current = _current()
    current["cases"] = current["cases"][:1]
    verdict = compare(_baseline(), current)
    assert verdict["verdict"] == "REGRESSION"
    assert any("case missing from current run: B" in r for r in verdict["regressions"])


def test_fixed_case_is_recorded_as_improvement():
    baseline = _baseline()
    baseline["cases"][1]["passed"] = False
    baseline["pass_rate"] = 0.5
    verdict = compare(baseline, _current())
    assert verdict["verdict"] == "PASS"
    assert any("B: failed in baseline, passes now" in i for i in verdict["improvements"])
