"""Runner: evaluate demo releases end to end.

For each release in releases.json:
  1. Run the project's own test suite through the CI step runner and
     feed the real pass/fail into the unit-test gate.
  2. Run the release-readiness gates.
  3. If the gates pass, simulate the canary rollout from the release's
     metric snapshots.
  4. Record the outcome in the SQLite history store and write a
     human-readable report per release.

Usage:  python run_release.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from release_automation.ci_runner import run_steps
from release_automation.gates import run_readiness_gates
from release_automation.history import (
    connect,
    record_release,
    record_rollout_event,
)
from release_automation.report import render_report
from release_automation.rollout import StageMetrics, simulate_canary_rollout

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "release_history" / "releases.db"
REPORTS_DIR = ROOT / "release_reports"


def main() -> int:
    config = json.loads((ROOT / "releases.json").read_text())
    REPORTS_DIR.mkdir(exist_ok=True)
    DB_PATH.parent.mkdir(exist_ok=True)

    # The unit-test gate uses a real CI step: this project's own test
    # suite, run through the subprocess step runner.
    ci_results = run_steps(
        [{"name": "unit_tests", "command": f"{sys.executable} -m pytest -q", "cwd": str(ROOT)}]
    )
    unit_tests_passed = all(r.passed for r in ci_results)
    tests_line = ci_results[0].stdout.strip().splitlines()[-1] if ci_results else "?"

    conn = connect(DB_PATH)
    summary = []
    for release in config["releases"]:
        release = dict(release)
        release.setdefault("ci", {})["unit_tests_passed"] = unit_tests_passed
        gate_report = run_readiness_gates(release)

        rollout = None
        if gate_report.passed:
            metrics = [StageMetrics(**m) for m in release["canary_metrics"]]
            rollout = simulate_canary_rollout(
                service=release["service"],
                version=release["version"],
                previous_version=release["rollback_plan"]["previous_version"],
                stage_metrics=metrics,
            )
            for stage in rollout.stages:
                record_rollout_event(
                    conn, release["service"], release["version"],
                    stage.stage_percent,
                    "promoted" if stage.promoted else "health gate failed",
                )
            for event in rollout.rollback_events:
                record_rollout_event(
                    conn, release["service"], release["version"],
                    rollout.stages[-1].stage_percent if rollout.stages else 0,
                    event,
                )

        record_release(
            conn,
            release["service"],
            release["version"],
            gate_report.passed_count,
            len(gate_report.results),
            gate_report.blocking_reasons,
        )

        report = render_report(gate_report, rollout)
        report_path = REPORTS_DIR / f"{release['service']}-{release['version']}.txt"
        report_path.write_text(report)
        print(report)
        print(f"Report written to {report_path}")
        print()
        summary.append(
            (release["service"], release["version"], gate_report, rollout)
        )

    print(f"CI step: unit tests {'PASSED' if unit_tests_passed else 'FAILED'} "
          f"({tests_line})")
    for service, version, gates, rollout in summary:
        if not gates.passed:
            state = f"BLOCKED ({gates.passed_count}/{len(gates.results)} gates)"
        elif rollout and rollout.rolled_back:
            state = f"ROLLED BACK at {rollout.stages[-1].stage_percent}%"
        elif rollout and rollout.completed:
            state = "SHIPPED (100%)"
        else:
            state = "no rollout"
        print(f"  {service} {version}: {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
