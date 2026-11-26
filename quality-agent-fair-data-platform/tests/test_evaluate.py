from quality_platform.agents import run_investigation
from quality_platform.evaluate import judge_trajectory, monitor, run_evals
from quality_platform.pipeline import build_system, run


def test_eval_suite_all_pass():
    _, _, client = build_system()
    summary = run_evals(client)
    assert summary["passed"] == summary["total"] == 6
    assert summary["pass_rate"] == 1.0
    assert all(c["missing_facts"] == [] for c in summary["cases"])


def test_judge_hard_fails_on_unverified_number():
    _, _, client = build_system()
    trajectory = run_investigation(
        "Why did batch release cycle time rise from Q2 to Q3?", client)
    trajectory["answer"] = trajectory["answer"] + " The worst batch took 99.9 days."
    from quality_platform.agents import validate
    trajectory["validation"] = validate(trajectory["answer"], trajectory["tool_calls"])
    judgement = judge_trajectory(trajectory)
    assert judgement["passed"] is False
    assert judgement["scores"]["numeric_accuracy"] == 0.0


def test_judge_hard_fails_on_tool_error():
    trajectory = {
        "tool_calls": [{"tool": "get_quality_metrics", "status": "error",
                        "error": "boom"}],
        "answer": "No answer.",
        "evidence": {"x": 1},
        "validation": {"passed": True, "unverified_numbers": []},
    }
    judgement = judge_trajectory(trajectory)
    assert judgement["scores"]["tool_use"] == 0.0
    assert judgement["passed"] is False


def test_monitor_no_runs():
    assert monitor([])["alert"] is False


def test_monitor_pass_rate_alert():
    health = monitor([{"pass_rate": 0.7, "mean_latency_ms": 100}])
    assert health["alert"] is True
    assert any("pass rate" in r for r in health["reasons"])


def test_monitor_latency_alert():
    health = monitor([{"pass_rate": 1.0, "mean_latency_ms": 100},
                      {"pass_rate": 1.0, "mean_latency_ms": 120}])
    assert health["alert"] is True
    assert any("latency" in r for r in health["reasons"])


def test_monitor_healthy():
    health = monitor([{"pass_rate": 1.0, "mean_latency_ms": 100},
                      {"pass_rate": 1.0, "mean_latency_ms": 105}])
    assert health["alert"] is False


def test_pipeline_report():
    report = run()
    assert report["investigation_passed"] is True
    assert report["evals_passed"] == 6
    assert report["monitor_alert"] is False
    assert len(report["products"]) == 3
