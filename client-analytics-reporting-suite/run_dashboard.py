"""Run the full client-analytics pipeline and print the summary.

Steps: generate synthetic data -> load into SQLite -> validate/QA ->
reconcile Python vs SQL aggregates -> compute KPIs and trends ->
write dashboard CSVs + HTML -> print the stakeholder summary.
Exits non-zero if any reconciliation mismatch is found.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client_analytics import analysis, dashboard, data, ingest, report, validate

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "client_analytics.db")
OUT_DIR = os.path.join(BASE, "dashboards")


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = ingest.open_db(DB_PATH)
    dataset = data.generate()
    ingest.load(conn, dataset)

    valid, txn_exceptions = validate.validate_transactions(conn)
    acct_exceptions = validate.validate_accounts(conn)
    exceptions = txn_exceptions + acct_exceptions
    mismatches = validate.reconcile_python_vs_sql(conn, valid)
    if mismatches:
        print(f"RECONCILIATION FAILED: {len(mismatches)} mismatches", file=sys.stderr)
        for m in mismatches:
            print(" ", m, file=sys.stderr)
        return 1

    monthly = analysis.month_over_month(analysis.kpi_by_month(valid))
    channels = analysis.kpi_by_channel(valid)
    top = analysis.top_clients(conn, valid)
    ops = analysis.ops_summary(conn)
    files = dashboard.build(OUT_DIR, monthly, channels, top, ops,
                            exceptions, mismatches)
    summary = report.build(monthly, channels, top, ops,
                           len(valid), len(dataset["transactions"]),
                           exceptions, mismatches)
    with open(os.path.join(OUT_DIR, "summary.txt"), "w") as f:
        f.write(summary)
    print(summary)
    print(f"Dashboard files written to {OUT_DIR}: {', '.join(files)}")
    print(f"Exceptions queued: {len(exceptions)} "
          f"({len(txn_exceptions)} transaction, {len(acct_exceptions)} account).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
