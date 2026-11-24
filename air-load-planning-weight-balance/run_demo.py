"""End-to-end demo: build a load plan, verify it, reconcile the scales,
and fan the finalized plan out over the event bus."""

from airload.load_plan import LoadPlan
from airload.messaging import Queue, Topic
from airload.report import text_load_sheet
from airload.scale_log import ScaleLog, ScaleReading
from airload.verification import verify_load_plan


def main() -> None:
    plan = LoadPlan(flight="AMZ101")
    plan.add_cargo("AKE12345", "FWD", 8_500.0)
    plan.add_cargo("AKE12346", "AFT", 7_200.0)
    plan.add_cargo("BULK01", "BULK", 2_800.0)
    plan.add_fuel(28_000.0)
    plan.finalize()
    print(text_load_sheet(plan))
    print()

    submitted = plan.to_dict()
    submitted["compartments"] = plan.compartment_totals()
    print(verify_load_plan(plan, submitted).summary())
    print()

    log = ScaleLog()
    log.record(ScaleReading("SCALE-1", "2026-11-24T10:15:00Z", "cargo:FWD:AKE12345", 8_510.0))
    log.record(ScaleReading("SCALE-2", "2026-11-24T10:17:00Z", "cargo:AFT:AKE12346", 7_190.0))
    log.record(ScaleReading("SCALE-3", "2026-11-24T10:19:00Z", "cargo:BULK:BULK01", 2_800.0))
    planned = {i.name: i.weight_lb for i in plan.items if i.name.startswith("cargo:")}
    findings = log.reconcile(planned)
    print("Scale reconciliation:", "clean" if not findings else findings)
    print()

    topic = Topic("load-plan-events")
    ops, audit = Queue("ops-load-plans"), Queue("audit-log")
    topic.subscribe(ops)
    topic.subscribe(audit)
    topic.publish("load_plan.finalized", plan.to_dict())
    delivered = 0
    while (msg := ops.receive()) is not None:
        ops.acknowledge(msg.message_id)
        delivered += 1
    print(f"Event bus: {delivered} message(s) delivered to ops, "
          f"{audit.pending_count} pending in audit, "
          f"{ops.dead_letter_count} dead-lettered")


if __name__ == "__main__":
    main()
