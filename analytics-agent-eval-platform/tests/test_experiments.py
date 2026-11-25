"""Tests for the A/B experiment analysis module."""

from agent_eval.experiments import analyze_experiment


def test_clear_win_recommends_ship():
    result = analyze_experiment(10000, 1000, 10000, 1150)
    assert result["recommendation"] == "SHIP"
    assert result["significant"] is True
    assert result["control_rate"] == 0.10
    assert result["treatment_rate"] == 0.115
    assert result["relative_uplift"] == 0.15
    assert result["srm"]["flagged"] is False


def test_clear_loss_recommends_no_ship():
    result = analyze_experiment(10000, 1000, 10000, 850)
    assert result["recommendation"] == "NO-SHIP"
    assert result["significant"] is True


def test_noisy_result_holds():
    result = analyze_experiment(500, 50, 500, 53)
    assert result["recommendation"] == "HOLD"
    assert result["significant"] is False
    assert any("not significant" in r for r in result["reasons"])


def test_small_sample_holds_without_p_value():
    result = analyze_experiment(20, 2, 20, 3)
    assert result["recommendation"] == "HOLD"
    assert result["p_value"] is None
    assert any("sample too small" in r for r in result["reasons"])


def test_srm_blocks_an_otherwise_significant_win():
    # 60/40 split with a real-looking lift: the result cannot be trusted.
    result = analyze_experiment(6000, 600, 4000, 480)
    assert result["srm"]["flagged"] is True
    assert result["recommendation"] == "HOLD"
    assert any("sample ratio mismatch" in r for r in result["reasons"])


def test_failed_guardrail_blocks_ship():
    result = analyze_experiment(
        10000, 1000, 10000, 1150,
        guardrails=[{"name": "retention", "control_rate": 0.80,
                     "treatment_rate": 0.70, "max_relative_drop": 0.05}])
    assert result["recommendation"] == "HOLD"
    assert result["failed_guardrails"][0]["name"] == "retention"


def test_opposing_segment_blocks_ship():
    result = analyze_experiment(
        10000, 1000, 10000, 1150,
        segments=[{"name": "mobile", "control_rate": 0.12,
                   "treatment_rate": 0.10}])
    assert result["recommendation"] == "HOLD"
    assert result["opposing_segments"] == ["mobile"]


def test_passing_guardrails_and_segments_still_ship():
    result = analyze_experiment(
        10000, 1000, 10000, 1150,
        guardrails=[{"name": "retention", "control_rate": 0.80,
                     "treatment_rate": 0.79, "max_relative_drop": 0.05}],
        segments=[{"name": "mobile", "control_rate": 0.10,
                   "treatment_rate": 0.115}])
    assert result["recommendation"] == "SHIP"
    assert result["failed_guardrails"] == []
    assert result["opposing_segments"] == []
