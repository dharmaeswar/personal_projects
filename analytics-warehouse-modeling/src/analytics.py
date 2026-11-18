"""Reporting queries over the star schema.

Each query joins the fact to its dimensions (never to raw events),
so the reports only ever see modelled, validated data.
"""
from __future__ import annotations

import sqlite3

QUERIES = {
    "service_adoption_trend": """
        SELECT d.year, d.month, s.service_code, s.service_name,
               COUNT(*) AS active_days,
               SUM(f.usage_qty) AS total_usage,
               SUM(f.cost_usd) AS total_cost_usd,
               COUNT(DISTINCT f.account_key) AS distinct_accounts
        FROM fact_service_usage f
        JOIN dim_date d    ON d.date_key = f.date_key
        JOIN dim_service s ON s.service_key = f.service_key
        GROUP BY d.year, d.month, s.service_code, s.service_name
        ORDER BY d.year, d.month, total_cost_usd DESC
    """,
    "revenue_driver_by_service_region": """
        SELECT s.service_code, r.region_code, r.region_name,
               SUM(f.cost_usd) AS total_cost_usd,
               SUM(f.usage_qty) AS total_usage,
               ROUND(100.0 * SUM(f.cost_usd) /
                     (SELECT SUM(cost_usd) FROM fact_service_usage), 2) AS pct_of_total_cost
        FROM fact_service_usage f
        JOIN dim_service s ON s.service_key = f.service_key
        JOIN dim_region r  ON r.region_key = f.region_key
        GROUP BY s.service_code, r.region_code, r.region_name
        ORDER BY total_cost_usd DESC
    """,
    "cost_per_account": """
        SELECT a.account_id, a.account_name, a.account_type, a.owner_team,
               COUNT(*) AS usage_days,
               SUM(f.cost_usd) AS total_cost_usd,
               ROUND(AVG(f.cost_usd), 2) AS avg_daily_cost_usd,
               MAX(f.cost_usd) AS max_daily_cost_usd
        FROM fact_service_usage f
        JOIN dim_account a ON a.account_key = f.account_key
        GROUP BY a.account_id, a.account_name, a.account_type, a.owner_team
        ORDER BY total_cost_usd DESC
    """,
    # Bonus: daily cost trend, useful as a freshness / trend sanity check.
    "daily_cost_trend": """
        SELECT d.date_value, SUM(f.cost_usd) AS total_cost_usd,
               SUM(f.usage_qty) AS total_usage
        FROM fact_service_usage f
        JOIN dim_date d ON d.date_key = f.date_key
        GROUP BY d.date_value
        ORDER BY d.date_value
    """,
}


def run_analytics(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    results = {}
    for name, sql in QUERIES.items():
        rows = conn.execute(sql).fetchall()
        results[name] = [dict(r) for r in rows]
    return results
