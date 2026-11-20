"""Tests for the qaops release-gate and health-check helpers.

Health checks run against the same sample API the framework tests use
(the session-scoped ``api_server`` fixture boots it). Gate tests use
synthetic summaries so the decision rules are checked in isolation.
"""
import json

import pytest

from qaops.gate import decide, report_json
from qaops.health import HealthCheck, all_healthy, check_config, check_environment


def test_health_check_ok(api_server):
    result = HealthCheck("health", api_server + "/health",
                         required_keys=("status",)).run()
    assert result["ok"] is True
    assert result["status"] == 200
    assert result["detail"] == "ok"


def test_health_check_missing_required_key(api_server):
    result = HealthCheck("health", api_server + "/health",
                         required_keys=("version",)).run()
    assert result["ok"] is False
    assert "version" in result["detail"]


def test_health_check_wrong_status(api_server):
    result = HealthCheck("missing", api_server + "/plans/999",
                         expected_status=200).run()
    assert result["ok"] is False
    assert result["status"] == 404


def test_health_check_expected_404_passes(api_server):
    result = HealthCheck("missing-404", api_server + "/plans/999",
                         expected_status=404,
                         required_keys=("error",)).run()
    assert result["ok"] is True


def test_health_check_unreachable_host_fails():
    result = HealthCheck("dead", "http://127.0.0.1:59999/health",
                         timeout_s=1.0).run()
    assert result["ok"] is False
    assert result["status"] is None
    assert "request failed" in result["detail"]


def test_check_config_ok_and_missing():
    assert check_config({"A": "x", "B": "y"}, ("A", "B"))["ok"] is True
    bad = check_config({"A": "x", "B": ""}, ("A", "B"))
    assert bad["ok"] is False
    assert "B" in bad["detail"]
    missing = check_config({}, ("API_BASE_URL",))
    assert missing["ok"] is False


def test_check_environment_and_all_healthy(api_server):
    results = check_environment(
        [HealthCheck("health", api_server + "/health"),
         HealthCheck("plans", api_server + "/plans")],
        config={"API_BASE_URL": api_server, "ENVIRONMENT": "staging"},
        config_keys=("API_BASE_URL", "ENVIRONMENT"),
    )
    assert len(results) == 3
    assert all_healthy(results) is True


def test_all_healthy_false_when_any_check_fails(api_server):
    results = check_environment(
        [HealthCheck("health", api_server + "/health"),
         HealthCheck("dead", "http://127.0.0.1:59999/health",
                     timeout_s=1.0)])
    assert all_healthy(results) is False


def _summary(passed=5, failed=0, skipped=0, error=0, names=None):
    return {"passed": passed, "failed": failed, "skipped": skipped,
            "error": error,
            "passed_names": names or [f"tests/test_x.py::test_{i}"
                                      for i in range(passed)]}


def test_gate_passes_when_everything_passes():
    report = decide(_summary(), required_checks=["tests/test_x.py::test_0"])
    assert report["verdict"] == "PASS"
    assert report["reasons"] == []
    assert report["pass_rate"] == 1.0


def test_gate_fails_on_any_failure():
    report = decide(_summary(passed=4, failed=1))
    assert report["verdict"] == "FAIL"
    assert any("1 test(s) failed" in r for r in report["reasons"])


def test_gate_fails_when_nothing_ran():
    report = decide({"passed": 0, "failed": 0, "skipped": 0, "error": 0,
                     "passed_names": []})
    assert report["verdict"] == "FAIL"
    assert "no tests ran" in report["reasons"]


def test_gate_fails_below_min_pass_rate():
    report = decide(_summary(passed=8, failed=2), min_pass_rate=0.9)
    assert report["verdict"] == "FAIL"
    assert any("pass rate" in r for r in report["reasons"])


def test_gate_fails_when_required_check_missing():
    report = decide(_summary(), required_checks=["tests/test_x.py::test_99"])
    assert report["verdict"] == "FAIL"
    assert any("required checks" in r for r in report["reasons"])


def test_gate_report_json_round_trips():
    report = decide(_summary())
    parsed = json.loads(report_json(report))
    assert parsed["verdict"] == "PASS"
    assert parsed["total"] == 5
