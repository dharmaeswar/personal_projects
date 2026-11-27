"""Scheduled ERM run: ingest -> RCSA -> KRI dashboard -> framework assessment
-> report. Writes erm_rcsa.db and reports/ (risk_report.txt plus CSVs that
open in Excel / import into Power BI) next to this file.
"""

from __future__ import annotations

from pathlib import Path

from erm_rcsa.data import AS_OF_DATE, generate_all
from erm_rcsa.frameworks import assess
from erm_rcsa.kri import kri_dashboard
from erm_rcsa.pipeline import connect, load_data, reconcile, top_loss_event
from erm_rcsa.rcsa import controls_testing_summary, rcsa_assessment
from erm_rcsa.reporting import (
    ExceptionQueue,
    dashboard_rows,
    render_report,
    signoff_checklist,
    write_csv,
)

ROOT = Path(__file__).resolve().parent

# Seeded 1LOD assessment results for the framework checklist.
ASSESSMENT_RESULTS = {
    "F-01": "Met", "F-02": "Partial", "F-03": "Not Met", "F-04": "Met",
    "F-05": "Partial", "F-06": "Met", "F-07": "Met", "F-08": "Partial",
    "F-09": "Met", "F-10": "Met", "F-11": "Partial", "F-12": "Met",
}


def main():
    data = generate_all()
    rcsa_rows = rcsa_assessment(data["risks"], data["controls"])
    kri_rows = kri_dashboard(data["kris"])
    framework = assess(data["framework_reqs"], ASSESSMENT_RESULTS)
    testing = controls_testing_summary(data["controls"])

    conn = connect(ROOT / "erm_rcsa.db")
    load_data(conn, data)
    recon = reconcile(data["loss_events"], conn)
    top_event = top_loss_event(conn)
    conn.close()
    if not recon["ok"]:
        raise SystemExit(f"reconciliation FAILED: {recon['mismatches']}")

    queue = ExceptionQueue()
    for k in kri_rows:
        if k["status"] == "BREACH":
            queue.add("BREACH", "KRI", k["kri_id"],
                      f"{k['name']} at {k['current']} {k['unit']} (breach {k['breach']})")
        elif k["status"] == "WARNING":
            queue.add("WARNING", "KRI", k["kri_id"],
                      f"{k['name']} at {k['current']} {k['unit']} (warning {k['warning']})")
    for r in rcsa_rows:
        if r["residual_band"] == "High":
            queue.add("High residual", "RCSA risk", r["risk_id"],
                      f"{r['name']} — residual {r['residual']}")
    for cid in testing["failing"]:
        queue.add("Ineffective control", "Control", cid, "ToE pass rate below 75% or design Ineffective")

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "risk_report.txt").write_text(
        render_report(AS_OF_DATE, rcsa_rows, kri_rows, framework, recon, top_event, queue),
        encoding="utf-8")
    write_csv(reports / "rcsa_results.csv", rcsa_rows,
              ["risk_id", "name", "category", "source", "inherent", "inherent_band",
               "residual", "residual_band", "controls", "control_ratings", "challenge"])
    write_csv(reports / "kri_dashboard.csv", kri_rows,
              ["kri_id", "name", "unit", "current", "warning", "breach", "status",
               "emerging_risk", "history"])
    write_csv(reports / "dashboard.csv", dashboard_rows(rcsa_rows, kri_rows),
              ["type", "id", "name", "category", "source", "value", "status"])
    write_csv(reports / "exceptions.csv", queue.ordered(),
              ["severity", "kind", "ref", "detail"])
    write_csv(reports / "framework_assessment.csv", framework["gaps"],
              ["req_id", "framework", "function", "requirement", "status"])
    write_csv(reports / "signoff_checklist.csv", signoff_checklist(),
              ["step", "check", "signed"])

    print(f"RCSA: {len(rcsa_rows)} risks, "
          f"{sum(1 for r in rcsa_rows if r['residual_band'] == 'High')} High residual")
    print(f"KRIs: {len(kri_rows)} tracked, "
          f"{sum(1 for k in kri_rows if k['status'] == 'BREACH')} BREACH, "
          f"{sum(1 for k in kri_rows if k['emerging_risk'])} emerging")
    print(f"Controls: {testing['effective']} Effective, "
          f"{testing['needs_improvement']} Needs Improvement, {testing['ineffective']} Ineffective")
    print(f"Framework coverage: {framework['overall_coverage']}%")
    print(f"Loss reconciliation: PASS ({len(data['loss_events'])} events)")
    print(f"Report written to {reports / 'risk_report.txt'}")


if __name__ == "__main__":
    main()
