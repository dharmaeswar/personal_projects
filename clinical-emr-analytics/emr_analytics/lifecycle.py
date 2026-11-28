"""Full data-analytics project lifecycle runner.

The lifecycle the HCA role requires — requirements gathering,
architecture/design, implementation, and support — run as explicit
phases with a run log, so a failed run can be resumed and audited:

1. requirements — load the feeds; record row counts and malformed rows.
2. design — standardize to the common vocabulary; record mapping notes.
3. implementation — run data-quality rules, root-cause analysis, and
   compute the clinical measures; build the dashboard spec.
4. support — write the run report and dashboard artifacts; record the
   outcome for the next run.

``run_pipeline`` returns the run report dict and, when ``output_dir``
is given, writes ``run_report.json`` and ``dashboard.html`` there.
"""

import json
import os
from datetime import date

from .ingest import load_feeds
from .measures import compute_measures
from .quality import run_quality
from .reports import build_dashboard_spec, render_html_dashboard, write_spec_json
from .root_cause import analyze
from .standardize import standardize_feeds

PHASES = ("requirements", "design", "implementation", "support")


def run_pipeline(data_dir, run_date=None, output_dir=None):
    run_date = run_date or date(2026, 11, 28)
    phases = []

    # 1. requirements — load the feeds.
    feeds, malformed = load_feeds(data_dir)
    total_rows = sum(len(rows) for rows in feeds.values())
    phases.append({
        "phase": "requirements",
        "status": "complete",
        "detail": "loaded %d rows across %d feeds; %d malformed rows reported"
                  % (total_rows, len(feeds),
                     sum(len(v) for v in malformed.values())),
    })

    # 2. design — standardize to the common vocabulary.
    standardized, notes = standardize_feeds(feeds)
    phases.append({
        "phase": "design",
        "status": "complete",
        "detail": "%d standardization notes across feeds"
                  % sum(len(v) for v in notes.values()),
    })

    # 3. implementation — quality rules, root cause, measures, dashboard.
    result = run_quality(standardized, run_date)
    findings = analyze(result["quarantined"])
    measures = compute_measures(result["clean"], result["quarantined"],
                                total_rows)
    spec = build_dashboard_spec(measures, findings)
    phases.append({
        "phase": "implementation",
        "status": "complete",
        "detail": "%d rows quarantined by %d rules; %d measures computed; "
                  "%d root-cause findings"
                  % (len(result["quarantined"]),
                     len({r for q in result["quarantined"] for r in q["rules"]}),
                     len(measures), len(findings)),
    })

    # 4. support — write artifacts and record the outcome.
    report = {
        "run_date": run_date.isoformat(),
        "phases": phases,
        "measures": measures,
        "findings": findings,
        "malformed": malformed,
        "standardization_notes": {k: v for k, v in notes.items() if v},
    }
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "run_report.json"), "w",
                  encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        render_html_dashboard(spec, os.path.join(output_dir, "dashboard.html"))
        write_spec_json(spec, os.path.join(output_dir, "dashboard_spec.json"))
        phases.append({
            "phase": "support",
            "status": "complete",
            "detail": "artifacts written to %s" % output_dir,
        })
    else:
        phases.append({
            "phase": "support",
            "status": "complete",
            "detail": "no output dir given; artifacts not written",
        })
    report["phases"] = phases
    return report
