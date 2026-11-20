"""Release-gate runner: health-check the environment, run the API suite,
then decide PASS/FAIL for the release candidate.

Usage (from the project root):

    python run_gate.py [--base-url http://127.0.0.1:8765] [--min-pass-rate 1.0]

Exit code 0 means the gate passed; 1 means it failed. The JSON gate
report is printed to stdout in both cases.
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request

import pytest

from qaops.gate import decide, report_json
from qaops.health import HealthCheck, all_healthy, check_environment
from sample_api.server import run as run_server

PORT = 8765
DEFAULT_BASE = f"http://127.0.0.1:{PORT}"
REQUIRED_CHECKS = [
    "tests/test_plans_api.py::test_health",
    "tests/test_plans_api.py::test_list_plans_schema",
]


class _Collector:
    """pytest plugin that records outcome counts and passed node ids."""

    def __init__(self):
        self.passed = []
        self.failed = 0
        self.skipped = 0
        self.error = 0

    def pytest_runtest_logreport(self, report):
        if report.outcome == "passed" and report.when == "call":
            self.passed.append(report.nodeid)
        elif report.outcome == "failed":
            self.failed += 1
        elif report.outcome == "skipped" and report.when == "call":
            self.skipped += 1
        elif report.outcome == "error":
            self.error += 1


def _wait_for_server(base, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def main(argv=None):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    thread = threading.Thread(target=run_server, kwargs={"port": PORT},
                              daemon=True)
    thread.start()
    if not _wait_for_server(base):
        print(json.dumps({"verdict": "FAIL",
                          "reasons": ["sample API did not start"]},
                         indent=2))
        return 1

    health_results = check_environment(
        [HealthCheck("health", base + "/health", required_keys=("status",)),
         HealthCheck("plans", base + "/plans", required_keys=("plans",)),
         HealthCheck("missing-plan-404", base + "/plans/999",
                     expected_status=404, required_keys=("error",))],
        config={"API_BASE_URL": base, "ENVIRONMENT": "staging"},
        config_keys=("API_BASE_URL", "ENVIRONMENT"),
    )
    if not all_healthy(health_results):
        print(json.dumps({"verdict": "FAIL", "stage": "health",
                          "health": health_results}, indent=2))
        return 1

    collector = _Collector()
    exit_code = pytest.main(["-q", "tests"], plugins=[collector])
    summary = {"passed": len(collector.passed), "failed": collector.failed,
               "skipped": collector.skipped, "error": collector.error,
               "passed_names": collector.passed}
    report = decide(summary, min_pass_rate=args.min_pass_rate,
                    required_checks=REQUIRED_CHECKS)
    report["health"] = health_results
    print(report_json(report))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
