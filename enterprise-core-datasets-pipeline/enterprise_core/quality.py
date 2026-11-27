"""Data-quality checks, reconciliation, and freshness SLA.

Every check returns a dict with a name, a pass/fail status, and the numbers
behind it, so a failed run says exactly what broke. A failed check blocks
publish: bad data never reaches the gold tables' consumers.
"""

import pandas as pd

FRESHNESS_SLA_DAYS = 2
RUN_DATE = "2026-11-26"  # the day this pipeline run is evaluated


def _check(name, passed, detail):
    return {"check": name, "passed": bool(passed), "detail": detail}


def run_checks(wh):
    """Run all checks against the warehouse. Returns a list of check dicts."""
    checks = []
    tables = wh.tables

    # --- schema: every expected table exists and has its key columns -------
    expected = {
        "fact_ai_usage_daily": ["date", "tool_name", "team", "events",
                                "tokens_in", "tokens_out", "cost_usd"],
        "fact_unit_economics_daily": ["date", "gbv_usd", "revenue_usd",
                                      "total_cost_usd", "margin_usd", "margin_pct"],
        "fact_cost_daily": ["date", "cost_category", "amount_usd"],
        "fact_jira_weekly": ["week_end", "project_key", "status",
                             "open_issues", "story_points"],
        "fact_payments_daily": ["date", "payment_method", "status",
                                "txn_count", "gross_amount_usd",
                                "settled_amount_usd", "avg_settlement_lag_days"],
        "dim_tool": ["tool_key", "tool_name", "price_per_1k_tokens",
                     "effective_from", "effective_to", "is_current"],
        "dim_payment_method": ["payment_method"],
    }
    for table, cols in expected.items():
        df = tables.get(table)
        ok = df is not None and not df.empty and all(c in df.columns for c in cols)
        checks.append(_check(f"schema:{table}", ok,
                             f"rows={0 if df is None else len(df)}"))

    # --- completeness: no nulls in key / measure columns -------------------
    for table, cols in expected.items():
        df = tables.get(table)
        if df is None or df.empty:
            continue
        nulls = int(df[cols].isna().sum().sum())
        checks.append(_check(f"completeness:{table}", nulls == 0, f"nulls={nulls}"))

    # --- uniqueness --------------------------------------------------------
    fact = tables.get("fact_ai_usage_daily")
    if fact is not None and not fact.empty:
        dupes = int(fact.duplicated(["date", "tool_name", "team"]).sum())
        checks.append(_check("uniqueness:fact_ai_usage_daily", dupes == 0,
                             f"duplicate_grains={dupes}"))
    ue = tables.get("fact_unit_economics_daily")
    if ue is not None and not ue.empty:
        dupes = int(ue.duplicated(["date"]).sum())
        checks.append(_check("uniqueness:fact_unit_economics_daily", dupes == 0,
                             f"duplicate_dates={dupes}"))
    pay_fact = tables.get("fact_payments_daily")
    if pay_fact is not None and not pay_fact.empty:
        dupes = int(pay_fact.duplicated(["date", "payment_method", "status"]).sum())
        checks.append(_check("uniqueness:fact_payments_daily", dupes == 0,
                             f"duplicate_grains={dupes}"))

    # --- ranges ------------------------------------------------------------
    if fact is not None and not fact.empty:
        bad = int(((fact["tokens_in"] < 0) | (fact["tokens_out"] < 0)
                   | (fact["cost_usd"] < 0)).sum())
        checks.append(_check("ranges:fact_ai_usage_daily", bad == 0, f"bad_rows={bad}"))
    if ue is not None and not ue.empty:
        bad = int(((ue["revenue_usd"] > ue["gbv_usd"])
                   | (ue["margin_pct"] < -1) | (ue["margin_pct"] > 1)).sum())
        checks.append(_check("ranges:fact_unit_economics_daily", bad == 0,
                             f"bad_rows={bad}"))
    if pay_fact is not None and not pay_fact.empty:
        bad = int(((pay_fact["gross_amount_usd"] < 0)
                   | (pay_fact["settled_amount_usd"] < 0)
                   | (pay_fact["settled_amount_usd"] > pay_fact["gross_amount_usd"])
                   | (pay_fact["txn_count"] <= 0)
                   | (pay_fact["avg_settlement_lag_days"] < 0)
                   | (pay_fact["avg_settlement_lag_days"] > 5)).sum())
        checks.append(_check("ranges:fact_payments_daily", bad == 0, f"bad_rows={bad}"))

    # --- referential integrity: fact keys exist in dims --------------------
    dim_tool = tables.get("dim_tool")
    if fact is not None and dim_tool is not None and not fact.empty:
        # point-in-time join: the fact's date must fall inside a dim_tool row
        missing = 0
        for _, r in fact.iterrows():
            match = dim_tool[(dim_tool["tool_name"] == r["tool_name"])
                             & (dim_tool["effective_from"] <= str(r["date"]))
                             & (dim_tool["effective_to"] >= str(r["date"]))]
            if match.empty:
                missing += 1
        checks.append(_check("referential:fact_ai_usage_daily->dim_tool",
                             missing == 0, f"unmatched_rows={missing}"))
    dim_team = tables.get("dim_team")
    if fact is not None and dim_team is not None and not fact.empty:
        unknown = set(fact["team"]) - set(dim_team["team"])
        checks.append(_check("referential:fact_ai_usage_daily->dim_team",
                             not unknown, f"unknown_teams={sorted(unknown)}"))
    dim_method = tables.get("dim_payment_method")
    if pay_fact is not None and dim_method is not None and not pay_fact.empty:
        unknown = set(pay_fact["payment_method"]) - set(dim_method["payment_method"])
        checks.append(_check("referential:fact_payments_daily->dim_payment_method",
                             not unknown, f"unknown_methods={sorted(unknown)}"))

    # --- SCD2 invariant: exactly one current row per tool ------------------
    if dim_tool is not None and not dim_tool.empty:
        current = dim_tool[dim_tool["is_current"] == 1]
        per_tool = current.groupby("tool_name").size()
        ok = (per_tool == 1).all() and set(per_tool.index) == set(dim_tool["tool_name"])
        checks.append(_check("scd2:dim_tool_single_current", bool(ok),
                             f"tools={len(per_tool)}"))

    # --- reconciliation: facts must tie back to bronze ---------------------
    bronze_ai = tables.get("bronze_ai_usage")
    if fact is not None and bronze_ai is not None and not fact.empty:
        diff = round(abs(float(fact["cost_usd"].sum()) - float(bronze_ai["cost_usd"].sum())), 4)
        checks.append(_check("reconciliation:fact_ai_cost_vs_bronze", diff == 0.0,
                             f"diff_usd={diff}"))
    bronze_bk = tables.get("bronze_bookings")
    if ue is not None and bronze_bk is not None and not ue.empty:
        diff = round(abs(float(ue["gbv_usd"].sum()) - float(bronze_bk["gbv_usd"].sum())), 2)
        checks.append(_check("reconciliation:fact_gbv_vs_bronze", diff == 0.0,
                             f"diff_usd={diff}"))
    costs = tables.get("fact_cost_daily")
    if ue is not None and costs is not None and not ue.empty:
        cost_total = float(costs.groupby("date")["amount_usd"].sum().sum())
        diff = round(abs(float(ue["total_cost_usd"].sum()) - cost_total), 2)
        checks.append(_check("reconciliation:fact_cost_daily_vs_unit_economics",
                             diff == 0.0, f"diff_usd={diff}"))
    bronze_pay = tables.get("bronze_payments")
    if pay_fact is not None and bronze_pay is not None and not pay_fact.empty:
        diff = round(abs(float(pay_fact["gross_amount_usd"].sum())
                         - float(bronze_pay["amount_usd"].sum())), 2)
        checks.append(_check("reconciliation:fact_payments_gross_vs_bronze",
                             diff == 0.0, f"diff_usd={diff}"))
        diff = round(abs(float(pay_fact["settled_amount_usd"].sum())
                         - float(bronze_pay["settled_amount_usd"].sum())), 2)
        checks.append(_check("reconciliation:fact_payments_settled_vs_bronze",
                             diff == 0.0, f"diff_usd={diff}"))
        diff = int(pay_fact["txn_count"].sum()) - len(bronze_pay)
        checks.append(_check("reconciliation:fact_payments_txn_count_vs_bronze",
                             diff == 0, f"diff_txns={diff}"))

    # --- freshness SLA: newest fact date within 2 days of the run date -----
    for fact_name, date_col in (("fact_ai_usage_daily", "date"),
                                ("fact_unit_economics_daily", "date"),
                                ("fact_payments_daily", "date")):
        df = tables.get(fact_name)
        if df is not None and not df.empty:
            newest = str(df[date_col].max())
            lag = (pd.Timestamp(RUN_DATE) - pd.Timestamp(newest)).days
            checks.append(_check(f"freshness:{fact_name}", lag <= FRESHNESS_SLA_DAYS,
                                 f"newest={newest} lag_days={lag}"))
    return checks


def all_passed(checks):
    return all(c["passed"] for c in checks)
