import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fin_impact import deploy, report, stats  # noqa: E402
from fin_impact import data  # noqa: E402


def test_wilson_interval_contains_estimate():
    lo, hi = stats.wilson_interval(50, 100)
    assert 0.0 <= lo <= 0.5 <= hi <= 1.0


def test_welch_finds_handle_time_drop():
    before = [16.0, 15.0, 17.0, 14.0, 16.5, 15.5]
    after = [6.0, 7.0, 5.5, 6.5, 7.0, 6.0]
    result = stats.welch_t_test(before, after)
    assert result["mean_a"] > result["mean_b"]
    assert result["p_value"] < 0.05


def test_uplift_interval_covers_point_estimate():
    result = stats.uplift(0.0, 0.5, 200, 200)
    assert result["ci_low"] <= result["uplift"] <= result["ci_high"]
    assert result["uplift"] == 0.5


def test_readiness_score_grades():
    full = {name: True for name, _, _ in deploy.READINESS_CHECKS}
    assert deploy.readiness_score(full)["grade"] == "ready"
    assert deploy.readiness_score(full)["score"] == 100
    assert deploy.readiness_score({})["grade"] == "not_ready"
    partial = {"volume_baseline": True, "kb_coverage": True,
               "escalation_path": True}
    assert deploy.readiness_score(partial)["grade"] == "ready_with_gaps"


def test_compare_arms_finds_real_uplift():
    convs = data.make_conversations(n_per_customer=200, seed=3)
    handle_test, esc_uplift = report.compare_arms(convs)
    assert esc_uplift["uplift"] > 0.3
    assert esc_uplift["ci_low"] > 0
    assert handle_test["p_value"] < 0.05


def test_product_feedback_flags_worst_channel():
    convs = data.make_conversations(n_per_customer=100, seed=4)
    from fin_impact import sql_analysis
    conn = sql_analysis.connect()
    sql_analysis.load(conn, convs)
    notes = report.product_feedback(sql_analysis.by_channel(conn),
                                    sql_analysis.metrics(conn))
    assert len(notes) >= 1
    assert any("channel" in n for n in notes)
