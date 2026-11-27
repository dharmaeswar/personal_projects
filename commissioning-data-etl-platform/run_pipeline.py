"""End-to-end run: extract from the APIs, load the warehouse, run the
quality checks, publish the dashboard datasets. Exits non-zero when any
quality check fails, so a scheduled run never publishes bad data.
"""

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from commissioning_etl.api_client import make_clients
from commissioning_etl.dashboards import daily_report, open_defects, system_progress, ticket_aging
from commissioning_etl.etl import run_pipeline
from commissioning_etl.quality import run_checks

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "output", "commissioning.db")
OUT_PATH = os.path.join(BASE, "output", "dashboard_summary.json")


def main():
    os.makedirs(os.path.join(BASE, "output"), exist_ok=True)
    clients = make_clients(os.path.join(BASE, "data"))
    summary = run_pipeline(clients, DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    checks = run_checks(conn)
    prog = system_progress(conn)
    defects = open_defects(conn)
    report = daily_report(conn)
    payload = {
        "summary": summary,
        "checks": checks,
        "systems": [list(r) for r in prog["systems"]],
        "areas": [list(r) for r in prog["areas"]],
        "ticket_aging": [list(r) for r in ticket_aging(conn)],
        "open_defects": [list(r) for r in defects],
    }
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    conn.close()
    print(report)
    print(f"\nETL: {summary}")
    failed = [c for c in checks if c["status"] == "fail"]
    print(f"Quality checks: {len(checks) - len(failed)}/{len(checks)} passed")
    for c in checks:
        print(f"  [{'PASS' if c['status'] == 'pass' else 'FAIL'}] {c['name']}: {c['detail']}")
    print(f"Dashboard dataset written to {OUT_PATH}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
