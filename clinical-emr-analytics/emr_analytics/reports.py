"""Standardized reports and a dashboard spec.

A standardized report is a fixed definition — name, grain, measures,
dimensions, filters, refresh cadence, audience — so every stakeholder
reads the same numbers the same way. The dashboard spec is the
Tableau / Power BI-style definition the reporting team would build
from: KPIs with values, the reports that feed them, and the filters a
user can apply. ``render_html_dashboard`` writes a static HTML page
from the spec (no JavaScript framework, no live data connection).
"""

import html
import json

REPORT_DEFS = [
    {
        "name": "Daily Clinical Quality Snapshot",
        "grain": "one row per encounter per day",
        "measures": ["vitals_completeness_pct", "data_quality_pass_rate_pct"],
        "dimensions": ["department", "encounter_type"],
        "filters": ["encounter_date", "department"],
        "refresh": "daily",
        "audience": "care operations leads",
    },
    {
        "name": "Lab Turnaround and Quality",
        "grain": "one row per lab result",
        "measures": ["lab_turnaround_median_hours", "data_quality_pass_rate_pct"],
        "dimensions": ["test_name", "department"],
        "filters": ["collected_at", "test_name"],
        "refresh": "daily",
        "audience": "laboratory and quality teams",
    },
    {
        "name": "Medication Reconciliation Coverage",
        "grain": "one row per encounter",
        "measures": ["med_reconciliation_pct"],
        "dimensions": ["department", "route"],
        "filters": ["encounter_date", "department"],
        "refresh": "weekly",
        "audience": "pharmacy and care teams",
    },
    {
        "name": "Data Quality and Root Cause Register",
        "grain": "one row per quarantined record",
        "measures": ["rows_quarantined", "data_quality_pass_rate_pct"],
        "dimensions": ["feed", "rule"],
        "filters": ["feed", "rule"],
        "refresh": "daily",
        "audience": "data engineering and analytics",
    },
]

KPI_LABELS = {
    "vitals_completeness_pct": "Vitals completeness (%)",
    "lab_turnaround_median_hours": "Median lab turnaround (hours)",
    "med_reconciliation_pct": "Medication reconciliation (%)",
    "data_quality_pass_rate_pct": "Data-quality pass rate (%)",
    "return_visit_rate_pct": "Return visits within 30 days (%)",
    "encounters_total": "Encounters",
    "patients_total": "Patients",
    "rows_quarantined": "Rows quarantined",
}


def build_dashboard_spec(measures, findings):
    """Build the dashboard definition from computed measures and
    root-cause findings."""
    kpis = []
    for key, label in KPI_LABELS.items():
        if key in measures and measures[key] is not None:
            kpis.append({"measure": key, "label": label,
                         "value": measures[key]})
    return {
        "title": "Clinical EMR Analytics — Standardized Dashboard",
        "kpis": kpis,
        "reports": REPORT_DEFS,
        "root_causes": findings,
        "filters": ["encounter_date", "department", "encounter_type"],
        "note": "All data is synthetic and seeded. No real patient data.",
    }


def render_html_dashboard(spec, path):
    """Write a static HTML dashboard from the spec. Returns the path."""
    rows = "".join(
        "<tr><td>%s</td><td>%s</td></tr>" % (html.escape(k["label"]),
                                            html.escape(str(k["value"])))
        for k in spec["kpis"])
    reports = "".join(
        "<li><b>%s</b> — grain: %s; measures: %s; refresh: %s; audience: %s</li>"
        % (html.escape(r["name"]), html.escape(r["grain"]),
           html.escape(", ".join(r["measures"])), html.escape(r["refresh"]),
           html.escape(r["audience"]))
        for r in spec["reports"])
    causes = "".join(
        "<li><b>%s / %s</b> — %d rows (%.1f%%): %s</li>"
        % (html.escape(f["feed"]), html.escape(f["rule"]), f["count"],
           f["share_pct"], html.escape(f["candidate_cause"]))
        for f in spec["root_causes"])
    page = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Clinical EMR Analytics Dashboard</title></head>
<body><h1>Clinical EMR Analytics — Standardized Dashboard</h1>
<p>All data is synthetic and seeded. No real patient data.</p>
<h2>Key measures</h2><table border="1"><tr><th>Measure</th><th>Value</th></tr>%s</table>
<h2>Standardized reports</h2><ul>%s</ul>
<h2>Top data-quality root causes</h2><ul>%s</ul>
</body></html>""" % (rows, reports, causes)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


def write_spec_json(spec, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    return path
