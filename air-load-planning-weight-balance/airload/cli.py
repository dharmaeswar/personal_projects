"""Command-line interface for the air load-planning demo."""

from __future__ import annotations

import argparse
import json
import sys

from .load_plan import LoadPlan
from .messaging import Queue, Topic
from .report import json_load_sheet, text_load_sheet
from .scale_log import ScaleLog, ScaleReading
from .verification import verify_load_plan
from .weight_balance import AircraftLimits


def build_demo_plan(flight: str = "AMZ101") -> LoadPlan:
    plan = LoadPlan(flight=flight)
    plan.add_cargo("AKE12345", "FWD", 8_500.0)
    plan.add_cargo("AKE12346", "AFT", 7_200.0)
    plan.add_cargo("BULK01", "BULK", 2_800.0)
    plan.add_fuel(28_000.0)
    plan.finalize()
    return plan


def cmd_plan(args: argparse.Namespace) -> int:
    plan = build_demo_plan(args.flight)
    print(text_load_sheet(plan))
    return 0 if plan.result and plan.result.within_envelope else 1


def cmd_verify(args: argparse.Namespace) -> int:
    plan = build_demo_plan(args.flight)
    submitted = plan.to_dict()
    submitted["compartments"] = plan.compartment_totals()
    if args.tamper:
        submitted["total_weight_lb"] += 5_000.0
    report = verify_load_plan(plan, submitted)
    print(report.summary())
    return 0 if report.passed else 1


def cmd_scales(args: argparse.Namespace) -> int:
    plan = build_demo_plan(args.flight)
    log = ScaleLog()
    log.record(ScaleReading("SCALE-1", "2026-11-24T10:15:00Z", "cargo:FWD:AKE12345", 8_510.0))
    log.record(ScaleReading("SCALE-2", "2026-11-24T10:17:00Z", "cargo:AFT:AKE12346", 7_190.0))
    log.record(ScaleReading("SCALE-3", "2026-11-24T10:19:00Z", "cargo:BULK:BULK01", 2_800.0))
    planned = {i.name: i.weight_lb for i in plan.items if i.name.startswith("cargo:")}
    findings = log.reconcile(planned)
    if findings:
        print("SCALE RECONCILIATION — mismatches:")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("SCALE RECONCILIATION — all cargo items reconcile within tolerance")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    plan = build_demo_plan(args.flight)
    topic = Topic("load-plan-events")
    ops_queue = Queue("ops-load-plans")
    audit_queue = Queue("audit-log")
    topic.subscribe(ops_queue)
    topic.subscribe(audit_queue)
    topic.publish("load_plan.finalized", plan.to_dict())
    delivered = 0
    while (msg := ops_queue.receive()) is not None:
        ops_queue.acknowledge(msg.message_id)
        delivered += 1
    print(
        f"SIMULATE — flight {plan.flight}: {delivered} message(s) delivered to "
        f"ops queue, {audit_queue.pending_count} pending in audit queue, "
        f"{ops_queue.dead_letter_count} dead-lettered"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="airload")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="build and print a demo load plan")
    p.add_argument("--flight", default="AMZ101")
    p.set_defaults(func=cmd_plan)
    v = sub.add_parser("verify", help="run auto load verification on a demo plan")
    v.add_argument("--flight", default="AMZ101")
    v.add_argument("--tamper", action="store_true",
                   help="corrupt the submitted total to prove ALV catches it")
    v.set_defaults(func=cmd_verify)
    s = sub.add_parser("scales", help="reconcile scale readings with the plan")
    s.add_argument("--flight", default="AMZ101")
    s.set_defaults(func=cmd_scales)
    m = sub.add_parser("simulate", help="fan a finalized plan out over the bus")
    m.add_argument("--flight", default="AMZ101")
    m.set_defaults(func=cmd_simulate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
