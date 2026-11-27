"""End-to-end run: seed -> DAG (ingest -> dims -> facts -> checks) -> report.

Writes Parquet tables and output/run_report.json. Exits non-zero when any
quality check fails, so a bad run never publishes.
"""

import json
import os
import sys

from enterprise_core import analytics, seed as seed_mod
from enterprise_core.backfill import run_backfill
from enterprise_core.orchestration import DagRunner, Task
from enterprise_core.pipeline import Warehouse
from enterprise_core.quality import all_passed, run_checks

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "output")


def run_pipeline(run_id="default", backfill=None):
    wh = Warehouse()
    feeds = seed_mod.seed_all()

    def ingest(feed):
        def _do():
            return wh.ingest(feed, feeds[feed])
        return _do

    tasks = [
        Task("ingest_ai_usage", [], ingest("ai_usage")),
        Task("ingest_jira", [], ingest("jira_issues")),
        Task("ingest_bookings", [], ingest("bookings")),
        Task("ingest_payments", [], ingest("payments")),
        Task("build_dims", ["ingest_ai_usage", "ingest_jira", "ingest_bookings",
                            "ingest_payments"],
             lambda: (wh.build_dims(), {"dims": sorted(
                 t for t in wh.tables if t.startswith("dim_"))})[1]),
        Task("build_facts", ["build_dims"], lambda: wh.build_facts()),
        Task("quality_checks", ["build_facts"], lambda: run_checks(wh)),
    ]
    runner = DagRunner(tasks)
    results = runner.run(run_id, {t.name: {"seed": 42} for t in tasks})
    checks = results["quality_checks"]

    backfill_report = None
    if backfill is not None:
        backfill_report = run_backfill(wh, *backfill)
        checks = run_checks(wh)

    os.makedirs(OUT, exist_ok=True)
    for name, df in wh.tables.items():
        df.to_parquet(os.path.join(OUT, f"{name}.parquet"), index=False)
    with open(os.path.join(OUT, "load_state.json"), "w") as fh:
        json.dump(wh.load_state, fh, indent=1, sort_keys=True)

    report = {
        "run_id": run_id,
        "ingest": {k: v for k, v in results.items() if k.startswith("ingest_")},
        "facts_added": results["build_facts"],
        "checks": checks,
        "checks_passed": all_passed(checks),
        "ai_cost_by_tool_month": analytics.ai_cost_by_tool_month(wh).to_dict("records"),
        "ai_cost_by_team": analytics.ai_cost_by_team(wh).to_dict("records"),
        "gbv_vs_revenue": analytics.gbv_vs_revenue(wh).to_dict("records"),
        "payments_settlement": analytics.payments_settlement_summary(wh).to_dict("records"),
        "backfill": backfill_report,
    }
    with open(os.path.join(OUT, "run_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    return wh, report


if __name__ == "__main__":
    _, report = run_pipeline()
    n_pass = sum(1 for c in report["checks"] if c["passed"])
    print(f"checks: {n_pass}/{len(report['checks'])} passed")
    for c in report["checks"]:
        if not c["passed"]:
            print("FAILED:", c["check"], c["detail"])
    print("facts added:", report["facts_added"])
    for row in report["gbv_vs_revenue"]:
        print("gbv/revenue:", row)
    sys.exit(0 if report["checks_passed"] else 1)
