"""Demo driver: register services, run an agent-driven rollout, report.

Usage: python run_platform.py [--report platform_report.txt]

All services and traffic are synthetic. The demo registers three
services (one deliberately fails a guardrail), rolls out the critical
checkout API through the agent workflow with human approvals, records
synthetic SLO samples, and prints a report to stdout and to a file.
"""
from __future__ import annotations

import argparse
import json

from delivery_platform import (
    AgentDataInterface,
    AgentWorkflow,
    AuditLog,
    OpsAgent,
    OpsIncident,
    RegionHealth,
    Service,
    ServiceRegistry,
    SLOTracker,
    evaluate_service,
    toil_report,
)


def build_registry() -> ServiceRegistry:
    registry = ServiceRegistry()
    registry.add(Service(
        name="checkout-api", team="payments", owner="dharma",
        backup_owner="priya", language="Java", repo="payments/checkout-api",
        criticality="critical", cpu_limit=2.0, memory_mb=2048,
        rollback_version="v1.42.0",
        rollback_steps=["shift traffic to v1.42.0", "verify error rate",
                        "close incident channel"],
    ))
    registry.add(Service(
        name="search-api", team="discovery", owner="dharma",
        backup_owner="priya", language="Python", repo="discovery/search-api",
        cpu_limit=1.0, memory_mb=1024,
        rollback_version="v2.18.3",
        rollback_steps=["shift traffic to v2.18.3", "verify latency"],
    ))
    # Deliberately non-compliant: no rollback version and no backup owner.
    registry.add(Service(
        name="billing-worker", team="payments", owner="dharma",
        backup_owner="dharma", language="Python",
        repo="payments/billing-worker", cpu_limit=8.0, memory_mb=16384,
        rollback_version="", rollback_steps=[], auto_rollback=False,
    ))
    return registry


def seed_slo(tracker: SLOTracker) -> None:
    # 200 synthetic samples for checkout-api: 199 ok, 1 slow error.
    for i in range(200):
        tracker.record("checkout-api", ok=(i != 137),
                       latency_ms=42.0 + (i % 17))
    for i in range(120):
        tracker.record("search-api", ok=True, latency_ms=18.0 + (i % 9))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="platform_report.txt")
    args = parser.parse_args()

    registry = build_registry()
    audit_log = AuditLog()
    tracker = SLOTracker()
    seed_slo(tracker)
    workflow = AgentWorkflow(audit_log)
    interface = AgentDataInterface(registry, audit_log, tracker)

    lines: list[str] = ["Agentic Service-Delivery Platform — report", ""]
    lines.append("Guardrail check")
    for service in registry.list():
        failed = [f.guardrail for f in evaluate_service(service)
                  if not f.passed]
        lines.append(f"  {service.name}: "
                     + ("compliant" if not failed
                        else "FAILED: " + ", ".join(failed)))

    service = registry.get("checkout-api")
    steps = workflow.plan_rollout(service)
    result = workflow.execute(
        service, steps,
        approvals={"canary-25": True, "canary-50": True,
                   "full-rollout": True},
        approver="human:dharma",
    )
    lines.append("")
    lines.append(f"Rollout {service.name}: "
                 + ("SUCCESS" if result["success"] else "BLOCKED"))
    for outcome in result["steps"]:
        lines.append(f"  {outcome['step']}: {outcome['outcome']}")
    lines.append(f"  final status: {service.status}")

    lines.append("")
    lines.append("SLO summary (checkout-api, target 0.999)")
    summary = interface.get_slo_summary("checkout-api")
    lines.append(f"  samples: {summary['samples']}")
    lines.append(f"  availability: {summary['availability']:.4f}")
    lines.append(f"  error budget remaining: "
                 f"{summary['error_budget_remaining']:.2f}")
    lines.append(f"  burn rate: {summary['burn_rate']:.1f}x")
    lines.append(f"  latency p95: {summary['latency_p95_ms']:.1f} ms")
    lines.append("  alerts: " + (", ".join(summary["alerts"]) or "none"))

    lines.append("")
    lines.append(f"Audit trail: {len(audit_log)} entries")
    for entry in audit_log.list(limit=5):
        lines.append(f"  [{entry.timestamp}] {entry.actor} {entry.action} "
                     f"-> {entry.decision} ({entry.reason})")

    lines.append("")
    lines.append("Agent query surface: "
                 + ", ".join(sorted(interface.describe_schema())))

    lines.append("")
    lines.append("Managed operations (agentic-first incident response)")
    regions = [
        RegionHealth(region="us-west-2", services=42, availability=0.9995,
                     open_incidents=1, manual_toil_hours=30.0,
                     automated_toil_hours=70.0),
        RegionHealth(region="us-east-1", services=38, availability=0.999,
                     open_incidents=0, manual_toil_hours=10.0,
                     automated_toil_hours=10.0),
    ]
    report_toil = toil_report(regions)
    lines.append(f"  regions tracked: {report_toil['regions']}")
    lines.append(f"  manual toil: {report_toil['manual_toil_hours']} h/week; "
                 f"automated toil: {report_toil['automated_toil_hours']} h/week")
    lines.append(f"  automation coverage: "
                 f"{report_toil['automation_coverage']:.1%}")
    for region_name, score in report_toil["health_scores"].items():
        lines.append(f"  health {region_name}: {score}/100")
    ops_agent = OpsAgent(audit_log)
    incident = OpsIncident("INC-101", "checkout-api", "sev2",
                           "elevated error rate on checkout-api")
    ops_action = ops_agent.propose(incident)
    ops_result = ops_agent.execute(incident, ops_action)
    lines.append(f"  incident {incident.incident_id} ({incident.severity}): "
                 f"{ops_action.name} -> {ops_result['outcome']} "
                 f"({ops_result['toil_saved_minutes']} toil minutes saved)")
    sev1 = OpsIncident("INC-102", "checkout-api", "sev1",
                       "region unavailable")
    sev1_action = ops_agent.propose(sev1)
    sev1_result = ops_agent.execute(sev1, sev1_action, approved=False)
    lines.append(f"  incident {sev1.incident_id} ({sev1.severity}): "
                 f"{sev1_action.name} -> {sev1_result['outcome']} "
                 f"(escalated, no approval given)")
    lines.append(f"  total toil saved by the ops agent: "
                 f"{ops_agent.toil_saved_minutes} minutes")
    report = "\n".join(lines) + "\n"
    print(report, end="")
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report)


if __name__ == "__main__":
    main()
