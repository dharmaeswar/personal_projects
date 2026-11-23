"""Demo entry point: run a full care-coordination workflow end to end.

All data is synthetic and de-identified (opaque PAT-#### references, no
names, no real health records). No network access.

Usage:
    python3 run_demo.py            # run the workflow once, print a summary
    python3 run_demo.py --serve    # run the workflow, then serve the HTTP API
"""

from __future__ import annotations

import argparse
import json

from care_coord.api import serve
from care_coord.service import CareCoordinationService

# Synthetic demo data: three de-identified patients, no PHI.
DEMO_PATIENTS = [
    {"patient_ref": "PAT-0001", "title": "Post-discharge follow-up",
     "goals": ["Schedule cardiology follow-up within 14 days", "Reconcile medications"]},
    {"patient_ref": "PAT-0002", "title": "Diabetes care coordination",
     "goals": ["Book endocrinology referral", "Arrange nutrition counselling"]},
    {"patient_ref": "PAT-0003", "title": "Annual wellness coordination",
     "goals": ["Complete lab work", "Schedule preventive screening"]},
]


def run_workflow(service: CareCoordinationService):
    delivered = []

    def handler(event):
        delivered.append(f"{event.event_type} ({event.aggregate_id[:6]})")

    report = []
    for patient in DEMO_PATIENTS:
        plan = service.create_care_plan(
            patient["patient_ref"], patient["title"], patient["goals"])
        service.transition_plan(plan.id, "active")
        ref = service.add_referral(plan.id, "cardiology",
                                   "follow-up after discharge", request_key=f"ref-{plan.id}")
        service.transition_referral(ref.id, "accepted")
        service.transition_referral(ref.id, "scheduled")
        task = service.create_task(plan.id, "Call patient to confirm appointment",
                                   assignee="care-team-1")
        service.transition_task(task.id, "in_progress")
        service.transition_task(task.id, "done")
        service.transition_referral(ref.id, "completed")
        service.transition_plan(plan.id, "completed")
        report.append((plan, ref, task))

    counts = service.process_outbox(handler)
    return report, counts, delivered, service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="serve the HTTP API after the demo")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    service = CareCoordinationService()
    report, counts, delivered, service = run_workflow(service)

    print(f"Care plans completed: {len(report)}")
    for plan, ref, task in report:
        print(f"  {plan.patient_ref} | {plan.title} | plan={plan.status.value} "
              f"referral={ref.status.value} task={task.status.value}")
    print(f"Outbox dispatch: {json.dumps(counts)}")
    print(f"Events delivered ({len(delivered)}):")
    for line in delivered:
        print(f"  - {line}")
    print(f"Audit entries: {len(service.store.audit)}")
    print(f"Pending outbox events: {len(service.store.pending_events())}")

    if args.serve:
        serve(service, args.port)


if __name__ == "__main__":
    main()
