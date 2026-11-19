"""Tests for ops/host_bottleneck.py (demo project)."""

from ops.host_bottleneck import demo_signals, diagnose, diagnosis_report


def test_healthy_host():
    result = diagnose(demo_signals("healthy"))
    assert result["verdict"] == "healthy"
    assert result["evidence"] == []


def test_cpu_bound_host():
    result = diagnose(demo_signals("cpu"))
    assert result["verdict"] == "cpu-bound"
    assert any("CPU utilisation 96%" in e for e in result["evidence"])
    assert "flamegraph" in result["next_check"]


def test_io_bound_host():
    result = diagnose(demo_signals("io"))
    assert result["verdict"] == "io-bound"
    assert any("IO wait 38%" in e for e in result["evidence"])
    assert "disk queue" in result["next_check"]


def test_memory_pressure_host():
    result = diagnose(demo_signals("memory"))
    assert result["verdict"] == "memory-pressure"
    assert any("memory use 94%" in e for e in result["evidence"])


def test_memory_wins_over_io():
    signals = demo_signals("io")
    signals["mem_used_pct"] = 95
    assert diagnose(signals)["verdict"] == "memory-pressure"


def test_high_load_without_high_cpu_is_cpu_bound():
    signals = demo_signals("healthy")
    signals["load_1m"] = 12.0
    result = diagnose(signals)
    assert result["verdict"] == "cpu-bound"
    assert any("per core" in e for e in result["evidence"])


def test_report_contains_verdict_and_next_check():
    report = diagnosis_report(demo_signals("cpu"))
    assert "Host verdict: cpu-bound" in report
    assert "Next check:" in report
