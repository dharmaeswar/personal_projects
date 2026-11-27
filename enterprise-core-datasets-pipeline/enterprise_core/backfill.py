"""Historical backfills with dependency analysis and a validation cutover.

A backfill reprocesses a date range instead of appending: it finds every fact
that depends on the affected source (via lineage), deletes that fact's rows
in the range, rebuilds them from bronze, re-runs the quality checks, and only
then commits the result. If the checks fail, the old rows stay in place.
"""

import pandas as pd

from .quality import run_checks, all_passed


def plan_backfill(wh, feed, start_date, end_date):
    """Return the facts a backfill of (feed, date range) touches."""
    bronze = f"bronze_{feed}"
    affected = []
    for table in ("fact_ai_usage_daily", "fact_unit_economics_daily",
                  "fact_cost_daily", "fact_jira_weekly", "fact_payments_daily"):
        if bronze in wh.lineage_for(table, exclude={"dim_date", "dim_team"}):
            affected.append(table)
    return {"feed": feed, "start": start_date, "end": end_date,
            "affected_facts": affected,
            "lineage": {t: wh.lineage_for(t, exclude={"dim_date", "dim_team"})
                        for t in affected}}


FACT_DATE_COL = {"fact_ai_usage_daily": "date",
                 "fact_unit_economics_daily": "date",
                 "fact_cost_daily": "date",
                 "fact_payments_daily": "date",
                 "fact_jira_weekly": "week_end"}


def run_backfill(wh, feed, start_date, end_date):
    """Execute the backfill. Returns a report; on check failure nothing is
    committed and the report says so."""
    plan = plan_backfill(wh, feed, start_date, end_date)
    # Snapshot the affected facts so a failed cutover can roll back.
    snapshot = {t: wh.tables[t].copy() for t in plan["affected_facts"]
                if t in wh.tables}
    for table in plan["affected_facts"]:
        df = wh.tables.get(table)
        if df is None or df.empty:
            continue
        date_col = FACT_DATE_COL[table]
        mask = (df[date_col].astype(str) >= start_date) & (df[date_col].astype(str) <= end_date)
        wh.tables[table] = df[~mask].reset_index(drop=True)
    # Reset the watermark for the touched facts so build_facts reloads them.
    for table in plan["affected_facts"]:
        wh.load_state.pop(table, None)
    # Rebuild only the backfilled range: temporarily trim bronze to the range,
    # build, then restore the full bronze table.
    bronze_name = f"bronze_{feed}"
    full_bronze = wh.tables[bronze_name]
    src_date = {"ai_usage": "event_date", "bookings": "booking_date",
                "jira_issues": "updated_date"}[feed]
    trimmed = full_bronze[(full_bronze[src_date].astype(str) >= start_date)
                          & (full_bronze[src_date].astype(str) <= end_date)]
    wh.tables[bronze_name] = trimmed
    added = wh.build_facts()
    wh.tables[bronze_name] = full_bronze
    # Restore watermarks to the full range so later incremental loads continue.
    for table in plan["affected_facts"]:
        date_col = FACT_DATE_COL[table]
        dates = wh.tables[table][date_col].astype(str) if table in wh.tables else pd.Series([], dtype=str)
        if len(dates):
            wh.load_state[table] = str(dates.max())
    checks = run_checks(wh)
    report = {"plan": plan, "rows_rebuilt": added,
              "checks_passed": all_passed(checks),
              "failed_checks": [c["check"] for c in checks if not c["passed"]]}
    if not report["checks_passed"]:
        for table, df in snapshot.items():
            wh.tables[table] = df
        report["cutover"] = "rolled back"
    else:
        report["cutover"] = "committed"
    return report
