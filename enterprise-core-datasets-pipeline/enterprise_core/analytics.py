"""Reporting queries over the gold tables only.

Analysts and finance partners read these, never bronze: every number here
comes from a fact or dimension, so definitions (what counts as AI cost, what
counts as margin) live in one place.
"""

import pandas as pd


def ai_cost_by_tool_month(wh):
    """AI spend by tool and month, with tokens and cost per 1k tokens."""
    fact = wh.tables["fact_ai_usage_daily"]
    df = fact.copy()
    df["month"] = df["date"].astype(str).str[:7]
    out = (df.groupby(["month", "tool_name"], as_index=False)
           .agg(events=("events", "sum"), tokens=("tokens_in", "sum"),
                cost_usd=("cost_usd", "sum")))
    out["cost_per_1k_tokens"] = (out["cost_usd"] / out["tokens"] * 1000).round(4)
    return out.sort_values(["month", "tool_name"]).reset_index(drop=True)


def ai_cost_by_team(wh):
    """AI spend share by team (who is driving adoption and cost)."""
    fact = wh.tables["fact_ai_usage_daily"]
    out = (fact.groupby("team", as_index=False)
           .agg(events=("events", "sum"), cost_usd=("cost_usd", "sum")))
    total = out["cost_usd"].sum()
    out["share_pct"] = (out["cost_usd"] / total * 100).round(2)
    return out.sort_values("cost_usd", ascending=False).reset_index(drop=True)


def unit_economics_trend(wh):
    """Daily GBV, revenue, total cost, and margin percent."""
    ue = wh.tables["fact_unit_economics_daily"]
    return ue.sort_values("date").reset_index(drop=True)


def jira_throughput(wh):
    """Done story points per week, by project (delivery throughput)."""
    weekly = wh.tables["fact_jira_weekly"]
    done = weekly[weekly["status"] == "Done"]
    out = (done.groupby(["week_end", "project_key"], as_index=False)
           .agg(done_points=("story_points", "sum"),
                done_issues=("open_issues", "sum")))
    return out.sort_values(["week_end", "project_key"]).reset_index(drop=True)


def gbv_vs_revenue(wh):
    """Critical-metrics check: GBV and revenue must stay in a sane band."""
    ue = wh.tables["fact_unit_economics_daily"]
    return pd.DataFrame({
        "total_gbv_usd": [round(float(ue["gbv_usd"].sum()), 2)],
        "total_revenue_usd": [round(float(ue["revenue_usd"].sum()), 2)],
        "revenue_share_of_gbv_pct": [
            round(float(ue["revenue_usd"].sum() / ue["gbv_usd"].sum() * 100), 2)],
        "avg_margin_pct": [round(float(ue["margin_pct"].mean() * 100), 2)],
    })
