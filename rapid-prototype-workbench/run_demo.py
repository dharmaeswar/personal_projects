"""Demo: two ideas -> prototypes -> feedback -> metrics -> decision.

Run: python3 run_demo.py [--port 8000]
Seeds two idea briefs (a developer-tools idea and a payment-experience
idea), scaffolds and launches both prototypes, feeds synthetic user
feedback through the pipeline, and prints metrics and the
iterate/pivot/kill decision for each. With --port, also serves the
prototype API + frontend pages until Ctrl-C.
"""

from __future__ import annotations

import argparse
import json
import threading

from prototype_lab.agent_tools import Workbench
from prototype_lab.feedback import decide
from prototype_lab.service import serve

SEED_IDEAS = [
    {
        "slug": "devtool-error-explainer",
        "title": "Plain-language API error explainer",
        "problem": "Developers waste hours decoding cryptic API error codes when integrating payments.",
        "target_user": "Developers integrating a payments API for the first time",
        "hypothesis": "A plain-language explanation with a one-click fix raises first-try success.",
        "success_metric": "70% of test developers complete a first charge without docs within 10 minutes",
    },
    {
        "slug": "one-tap-tip-jar",
        "title": "One-tap tip jar for creators",
        "problem": "Small creators lose tips because checkout asks for too much information for a $2 tip.",
        "target_user": "Creators with small audiences who receive small tips",
        "hypothesis": "A one-tap $2 tip with no account raises completed tips per visitor.",
        "success_metric": "Tip completion rate above 25% across 100 test visitors",
    },
]

SEED_FEEDBACK = [
    # error explainer: users love it (iterate)
    *[{"user_id": f"dev-{i:02d}", "prototype_slug": "devtool-error-explainer-v1",
       "rating": r, "comment": "fixed my error on the first try",
       "day": "2026-11-26"} for i, r in enumerate([5, 5, 4, 5, 4, 5, 4, 5, 5, 4, 5, 4])],
    # tip jar: middling (pivot)
    *[{"user_id": f"fan-{i:02d}", "prototype_slug": "one-tap-tip-jar-v1",
       "rating": r, "comment": "fast, but I wanted to pick the amount",
       "day": "2026-11-26"} for i, r in enumerate([3, 4, 3, 2, 4, 3, 3, 4, 2, 3, 4, 3])],
]


def build_workbench():
    wb = Workbench()
    for idea in SEED_IDEAS:
        wb.ideas.create(**idea)
        proto = wb.prototypes.scaffold(wb.ideas.get(idea["slug"]), build_minutes=180)
        wb.prototypes.launch(idea["slug"])
        wb.ideas.set_status(idea["slug"], "prototyping")
    counts = wb.pipeline.ingest_many(SEED_FEEDBACK)
    return wb, counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0, help="serve the prototype API on this port")
    args = parser.parse_args()

    wb, counts = build_workbench()
    print(f"feedback ingest: {counts}")
    for idea in SEED_IDEAS:
        slug = f"{idea['slug']}-v1"
        metrics = wb.pipeline.metrics(slug)
        decision, reason = decide(metrics)
        print(f"\n{slug}: {json.dumps(metrics)}")
        print(f"decision: {decision} — {reason}")

    if args.port:
        server = serve(wb.ideas, wb.prototypes, wb.pipeline, port=args.port)
        print(f"\nserving prototype API + pages on http://127.0.0.1:{args.port} (Ctrl-C to stop)")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            server.shutdown()


if __name__ == "__main__":
    main()
