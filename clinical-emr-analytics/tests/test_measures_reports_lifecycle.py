"""Tests for measures, reports, SQL, and the full lifecycle."""

import json
import os

from emr_analytics.ingest import load_feeds
from emr_analytics.lifecycle import run_pipeline
from emr_analytics.measures import compute_measures
from emr_analytics.quality import run_quality
from emr_analytics.reports import (
    REPORT_DEFS,
    build_dashboard_spec,
    render_html_dashboard,
)
from emr_analytics.root_cause import analyze
from emr_analytics.standardize import standardize_feeds

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")


def _measures():
    feeds, _ = load_feeds(DATA)
    standardized, _ = standardize_feeds(feeds)
    result = run_quality(standardized)
    total = sum(len(rows) for rows in feeds.values())
    return compute_measures(result["clean"], result["quarantined"], total)


def test_measure_totals():
    m = _measures()
    assert m["encounters_total"] == 12
    assert m["patients_total"] == 8
    assert m["rows_total"] == 96
    assert m["rows_quarantined"] == 12


def test_vitals_completeness():
    # E003 lost its heart rate, E005 lost its SpO2 — 10 of 12 complete.
    assert _measures()["vitals_completeness_pct"] == 83.33


def test_lab_turnaround_median():
    assert _measures()["lab_turnaround_median_hours"] == 3.79


def test_med_reconciliation():
    assert _measures()["med_reconciliation_pct"] == 100.0


def test_data_quality_pass_rate():
    assert _measures()["data_quality_pass_rate_pct"] == 87.5


def test_return_visit_rate():
    # PAT-001 (27 days) and PAT-002 (23 days) returned within 30 days.
    assert _measures()["return_visit_rate_pct"] == 25.0


def test_four_standardized_reports():
    assert len(REPORT_DEFS) == 4
    names = {r["name"] for r in REPORT_DEFS}
    assert "Daily Clinical Quality Snapshot" in names
    assert "Data Quality and Root Cause Register" in names
    for report in REPORT_DEFS:
        assert report["measures"] and report["dimensions"]
        assert report["refresh"] in ("daily", "weekly")


def test_dashboard_spec_has_all_kpis():
    m = _measures()
    spec = build_dashboard_spec(m, [])
    labels = {k["measure"] for k in spec["kpis"]}
    assert "vitals_completeness_pct" in labels
    assert "lab_turnaround_median_hours" in labels
    assert "data_quality_pass_rate_pct" in labels
    assert spec["reports"] == REPORT_DEFS


def test_html_dashboard_contains_values(tmp_path):
    m = _measures()
    feeds, _ = load_feeds(DATA)
    standardized, _ = standardize_feeds(feeds)
    result = run_quality(standardized)
    findings = analyze(result["quarantined"])
    spec = build_dashboard_spec(m, findings)
    path = render_html_dashboard(spec, str(tmp_path / "dash.html"))
    text = open(path, encoding="utf-8").read()
    assert "83.33" in text
    assert "87.5" in text
    assert "OUT_OF_RANGE" in text


def test_bigquery_sql_structured():
    sql = open(os.path.join(BASE, "emr_analytics", "sql", "measures.sql"),
               encoding="utf-8").read()
    for cte in ("vitals_completeness", "lab_turnaround", "med_reconciliation",
                "data_quality", "return_visits"):
        assert cte in sql
    for measure in ("vitals_completeness_pct", "lab_turnaround_median_hours",
                    "med_reconciliation_pct", "data_quality_pass_rate_pct",
                    "return_visit_rate_pct"):
        assert measure in sql
    assert sql.count("(") == sql.count(")")


def test_full_pipeline_phases_and_artifacts(tmp_path):
    report = run_pipeline(DATA, output_dir=str(tmp_path))
    phases = [p["phase"] for p in report["phases"]]
    assert phases == ["requirements", "design", "implementation", "support"]
    assert all(p["status"] == "complete" for p in report["phases"])
    assert report["measures"]["rows_quarantined"] == 12
    assert os.path.exists(os.path.join(str(tmp_path), "run_report.json"))
    assert os.path.exists(os.path.join(str(tmp_path), "dashboard.html"))
    assert os.path.exists(os.path.join(str(tmp_path), "dashboard_spec.json"))
    saved = json.load(open(os.path.join(str(tmp_path), "run_report.json"),
                           encoding="utf-8"))
    assert saved["measures"]["vitals_completeness_pct"] == 83.33
