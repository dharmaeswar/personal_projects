"""Runner: evaluate the fleet's deployment templates end to end.

For each service in services.json:
  1. Register its deployment template.
  2. Run the policy engine's guardrails over it.
  3. Combine the decision with its SLO / error-budget / incident
     numbers into a fleet safety score.
  4. Record the decision in the SQLite audit log.
  5. Build the on-call checklist for the riskiest service.

Then write the fleet rollout report and print a summary.

Usage:  python run_platform.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from deployment_guardrails.audit import (
    connect,
    decisions_on_date,
    record_decision,
    rejection_count,
)
from deployment_guardrails.fleet import FleetDashboard, FleetService
from deployment_guardrails.policies import evaluate_template
from deployment_guardrails.report import render_fleet_report
from deployment_guardrails.templates import DeploymentTemplate, Registry

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "fleet_data" / "guardrails.db"
REPORT_PATH = ROOT / "fleet_reports" / "fleet-report.txt"


def main() -> int:
    config = json.loads((ROOT / "services.json").read_text())
    registry = Registry()
    registry.register_many(
        DeploymentTemplate.from_dict(s) for s in config["services"]
    )

    dashboard = FleetDashboard()
    conn = connect(DB_PATH)
    decided_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    today = decided_at[:10]

    total_violations = 0
    for raw in config["services"]:
        template = registry.get(raw["service"])
        decision = evaluate_template(template)
        total_violations += len(decision.violations)
        record_decision(
            conn, decision, raw.get("requested_by", "unknown"), decided_at
        )
        dashboard.add(
            FleetService(
                service=raw["service"],
                version=raw["version"],
                slo_target=raw["slo_target"],
                availability=raw["availability"],
                error_budget_remaining_pct=raw["error_budget_remaining_pct"],
                open_incidents=raw["open_incidents"],
                decision=decision,
            )
        )

    report = render_fleet_report(dashboard)
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(report)
    print(report)
    print(f"Report written to {REPORT_PATH}")
    print(f"Audit log: {DB_PATH}")

    print(
        f"Services checked: {dashboard.service_count}  "
        f"Deployable: {dashboard.deployable_count}  "
        f"Blocked: {dashboard.blocked_count}  "
        f"Guardrail violations: {total_violations}"
    )
    print(
        f"Average safety score: {dashboard.average_safety_score}/100  "
        f"Audit entries today: {len(decisions_on_date(conn, today))}  "
        f"Total rejections on record: {rejection_count(conn)}"
    )
    for service in dashboard.services:
        print(
            f"  {service.service} {service.version}: "
            f"{service.status} (safety {service.safety_score}/100, "
            f"{service.decision.passed_count}/"
            f"{service.decision.total_count} guardrails)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
