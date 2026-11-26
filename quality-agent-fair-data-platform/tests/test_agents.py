from quality_platform.agents import (
    analyse,
    plan,
    retrieve,
    run_investigation,
    validate,
)
from quality_platform.pipeline import build_system


def test_plan_includes_baseline_and_current():
    steps = plan("Why did batch release cycle time rise from Q2 to Q3?")
    tools = [s["tool"] for s in steps]
    assert tools.count("get_quality_metrics") == 3
    assert "run_quality_check" in tools


def test_investigation_passes_and_is_grounded():
    _, _, client = build_system()
    result = run_investigation(
        "Why did batch release cycle time rise from Q2 to Q3?", client)
    assert result["passed"] is True
    assert "20.0" in result["answer"] and "27.5" in result["answer"]
    assert "7.5" in result["answer"]
    assert "documentation" in result["answer"]
    assert result["validation"]["passed"] is True
    assert result["validation"]["unverified_numbers"] == []


def test_investigation_tool_calls_all_ok():
    _, _, client = build_system()
    result = run_investigation("Why did batch release cycle time rise?", client)
    assert all(c["status"] == "ok" for c in result["tool_calls"])
    assert len(result["tool_calls"]) == len(result["steps"])


def test_analyse_missing_metrics_declines():
    result = analyse("Why?", [])
    assert result["grounded"] is False
    assert "cannot answer" in result["answer"].lower()


def test_validate_catches_hallucinated_number():
    _, _, client = build_system()
    steps = plan("Why did batch release cycle time rise?")
    calls = retrieve(client, steps)
    check = validate("Mean rose from 20.0 days to 99.9 days.", calls)
    assert check["passed"] is False
    assert "99.9" in check["unverified_numbers"]


def test_validate_accepts_true_numbers():
    _, _, client = build_system()
    steps = plan("Why did batch release cycle time rise?")
    calls = retrieve(client, steps)
    check = validate("Mean rose from 20.0 days in Q2 to 27.5 days in Q3.", calls)
    assert check["passed"] is True
