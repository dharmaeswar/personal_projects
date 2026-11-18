"""Scheduled risk-report run: ingest -> limits -> stress -> report.

Writes risk_reporting.db, reports/risk_report.txt and the CSV outputs
(limit_breaches.csv, stress_results.csv, exceptions.csv,
signoff_checklist.csv) next to this file.
"""

from __future__ import annotations

from pathlib import Path

from risk_reporting.data import AS_OF_DATE, generate_all
from risk_reporting.limits import aggregate_exposures, breaches
from risk_reporting.pipeline import (
    connect,
    create_tables,
    load_data,
    reconcile,
    sql_limit_results,
    store_results,
)
from risk_reporting.report import render_report, write_csv, write_outputs
from risk_reporting.stress import run_all_scenarios
from risk_reporting.workflow import (
    ExceptionQueue,
    SignoffChecklist,
    scheduled_run_summary,
)

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "risk_reporting.db"
REPORTS_DIR = ROOT / "reports"


def main() -> dict:
    data = generate_all()
    positions, limits = data["positions"], data["limits"]

    limit_results, data_exceptions = aggregate_exposures(positions, limits)
    stress_results = run_all_scenarios()

    conn = connect(DB_PATH)
    try:
        create_tables(conn)
        load_data(conn, positions, limits)
        sql_results = sql_limit_results(conn)
        store_results(conn, limit_results, stress_results)
    finally:
        conn.close()
    reconciliation = reconcile(limit_results, sql_results)

    queue = ExceptionQueue()
    queue.add_breaches(limit_results)
    queue.add_data_exceptions(data_exceptions)
    # Stress breaches join the queue too.
    for s in stress_results:
        if s.status == "BREACH":
            queue.items.append({
                "trade_id": "",
                "desk": "Liquidity Management",
                "risk_type": "Liquidity Gap",
                "reason": (
                    f"liquidity stress breach in {s.scenario} scenario: "
                    f"coverage ratio {s.coverage_ratio:.2f} "
                    f"(liquid assets {s.liquid_assets} vs stressed "
                    f"outflows {s.stressed_outflows})"
                ),
                "severity": "HIGH",
            })

    checklist = SignoffChecklist.fresh()

    text = render_report(AS_OF_DATE, limit_results, stress_results,
                         queue.sorted(), reconciliation)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "risk_report.txt").write_text(text, encoding="utf-8")
    paths = write_outputs(REPORTS_DIR, limit_results, stress_results,
                          queue.sorted())
    write_csv(
        REPORTS_DIR / "signoff_checklist.csv",
        ["item", "status", "signed_by"],
        [[row["item"], row["status"], row["signed_by"]]
         for row in checklist.items],
    )

    summary = {
        "as_of_date": AS_OF_DATE,
        "positions": len(positions),
        "limits_checked": len(limit_results),
        "breaches": len(breaches(limit_results)),
        "warnings": sum(1 for r in limit_results if r.status == "WARNING"),
        "exceptions": len(queue.items),
        "stress": {s.scenario: s.coverage_ratio for s in stress_results},
        "stress_breaches": [s.scenario for s in stress_results
                            if s.status == "BREACH"],
        "reconciliation_mismatches": len(reconciliation),
    }
    print(text)
    print(scheduled_run_summary(
        AS_OF_DATE, summary["positions"], summary["limits_checked"],
        summary["breaches"], summary["exceptions"]))
    print(f"Outputs: {REPORTS_DIR}/")
    return summary


if __name__ == "__main__":
    main()
