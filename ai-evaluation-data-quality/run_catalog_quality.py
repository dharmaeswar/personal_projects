"""Run the catalog-quality pipeline on the synthetic catalog.

Normalizes every listing, runs the defect checks, feeds seller feedback
and customer signals into the self-learning loop, applies only the
auto-corrections whose rule is trusted, and scores the corrections
against known-correct values behind the evaluation guardrail.

Writes catalog_quality_report.json and catalog_quality_report.txt next
to this script and prints the report. Exits 1 when the defect gate fails
(any critical finding) — the synthetic catalog plants nine defects on
purpose, so a FAIL gate here means the pipeline is catching them, not
that it is broken.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eval_quality.catalog import (
    FeedbackLoop,
    evaluate_corrections,
    normalize_product,
    run_catalog_checks,
)
from eval_quality.catalog_samples import (
    CORRECTION_LABELS,
    CUSTOMER_SIGNALS,
    FEEDBACK_EVENTS,
    PROPOSED_CORRECTIONS,
    build_catalog,
)


def main():
    products = build_catalog()
    normalized = [normalize_product(p) for p in products]
    report = run_catalog_checks(products)

    loop = FeedbackLoop()
    for rule_id, accepted in FEEDBACK_EVENTS:
        loop.ingest_feedback(rule_id, accepted)
    for record_id, signal_type in CUSTOMER_SIGNALS:
        loop.ingest_signal(record_id, signal_type)

    _, applied, blocked = loop.apply_corrections(
        normalized, PROPOSED_CORRECTIONS
    )
    proposed = [
        (c["record_id"], c["field"], c["new_value"]) for c in PROPOSED_CORRECTIONS
    ]
    evaluation = evaluate_corrections(proposed, CORRECTION_LABELS)

    report["self_learning"] = {
        "rule_weights": {
            rule: loop.weight(rule) for rule in sorted(loop.rules)
        },
        "auto_correct_allowed": {
            rule: loop.should_auto_correct(rule) for rule in sorted(loop.rules)
        },
        "flagged_records": loop.flagged_records(),
        "corrections_applied": len(applied),
        "corrections_blocked": len(blocked),
        "blocked": [
            {"record_id": c["record_id"], "field": c["field"],
             "rule_id": c["rule_id"]} for c in blocked
        ],
    }
    report["evaluation_guardrail"] = evaluation

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "catalog_quality_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(here, "catalog_quality_report.txt"), "w") as fh:
        fh.write(render_text(report))
    print(render_text(report))
    return 0 if report["summary"]["gate"] == "PASS" else 1


def render_text(report):
    summary = report["summary"]
    lines = [
        "CATALOG QUALITY REPORT",
        "=" * 40,
        "Products checked: %d" % summary["total_products"],
        "Findings: %d (%d critical, %d warnings)"
        % (summary["total_findings"], summary["critical"],
           summary["warnings"]),
        "Quality gate: %s" % summary["gate"],
        "",
        "Findings by check:",
    ]
    for check, count in sorted(summary["findings_by_check"].items()):
        lines.append("  - %s: %d" % (check, count))
    lines.append("")
    lines.append("Findings:")
    for finding in report["findings"]:
        lines.append("  [%s] %s | %s | %s"
                     % (finding["severity"], finding["check"],
                        finding["record_id"], finding["detail"]))
    loop = report["self_learning"]
    lines.append("")
    lines.append("Self-learning loop:")
    for rule, weight in sorted(loop["rule_weights"].items()):
        lines.append("  - %s: weight %.3f, auto-correct %s"
                     % (rule, weight, loop["auto_correct_allowed"][rule]))
    lines.append("  - records flagged by customer signals: %s"
                 % (", ".join(loop["flagged_records"]) or "(none)"))
    lines.append("  - corrections applied: %d, blocked: %d"
                 % (loop["corrections_applied"], loop["corrections_blocked"]))
    guard = report["evaluation_guardrail"]
    lines.append("")
    lines.append("Evaluation guardrail: %s (precision %.3f, recall %.3f, "
                 "%d of %d corrections correct)"
                 % (guard["gate"], guard["precision"], guard["recall"],
                    guard["correct"], guard["proposed"]))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
