"""Advanced SQL against Finance data — real queries, executed.

A small in-memory SQLite warehouse holds revenue, billings and close
rows, and the queries use the techniques the posting names: CTEs,
window functions (running totals, LAG for year-over-year growth,
RANK), and complex joins. These are the same shapes a Databricks SQL
warehouse would run; SQLite here keeps the project dependency-free
and the tests fast.
"""

from __future__ import annotations

import sqlite3


SCHEMA = """
CREATE TABLE revenue (
    month TEXT, segment TEXT, amount_minor INTEGER
);
CREATE TABLE billings (
    invoice_id TEXT, month TEXT, segment TEXT, amount_minor INTEGER,
    recognised_minor INTEGER
);
CREATE TABLE close_tasks (
    task_id TEXT, month TEXT, status TEXT
);
"""

MONTHLY_RUNNING_TOTAL = """
WITH monthly AS (
    SELECT month, SUM(amount_minor) AS month_total
    FROM revenue
    GROUP BY month
)
SELECT month, month_total,
       SUM(month_total) OVER (ORDER BY month
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
           AS running_total_minor
FROM monthly
ORDER BY month
"""

YOY_GROWTH = """
WITH monthly AS (
    SELECT month, SUM(amount_minor) AS month_total
    FROM revenue
    GROUP BY month
)
SELECT month, month_total,
       LAG(month_total) OVER (ORDER BY month) AS prior_month_total,
       ROUND(100.0 * (month_total
           - LAG(month_total) OVER (ORDER BY month))
           / NULLIF(LAG(month_total) OVER (ORDER BY month), 0), 2)
           AS growth_pct
FROM monthly
ORDER BY month
"""

SEGMENT_RANK = """
SELECT segment, SUM(amount_minor) AS total_minor,
       RANK() OVER (ORDER BY SUM(amount_minor) DESC) AS revenue_rank
FROM revenue
GROUP BY segment
ORDER BY revenue_rank
"""

UNRECOGNISED_BILLINGS = """
SELECT b.invoice_id, b.month, b.segment,
       b.amount_minor - b.recognised_minor AS unrecognised_minor
FROM billings b
LEFT JOIN revenue r
  ON r.month = b.month AND r.segment = b.segment
WHERE b.amount_minor > b.recognised_minor
ORDER BY b.month, b.invoice_id
"""

CLOSE_STATUS = """
SELECT c.month,
       COUNT(*) AS tasks,
       SUM(CASE WHEN c.status = 'done' THEN 1 ELSE 0 END)
           AS tasks_done,
       ROUND(100.0 * SUM(CASE WHEN c.status = 'done' THEN 1 ELSE 0 END)
           / COUNT(*), 1) AS pct_done
FROM close_tasks c
GROUP BY c.month
ORDER BY c.month
"""


class FinanceWarehouse:
    """In-memory SQLite warehouse seeded with caller-supplied rows."""

    def __init__(self, revenue=(), billings=(), close_tasks=()) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)
        self.conn.executemany(
            "INSERT INTO revenue VALUES (?, ?, ?)", list(revenue))
        self.conn.executemany(
            "INSERT INTO billings VALUES (?, ?, ?, ?, ?)",
            list(billings))
        self.conn.executemany(
            "INSERT INTO close_tasks VALUES (?, ?, ?)",
            list(close_tasks))
        self.conn.commit()

    def monthly_running_total(self) -> list[dict]:
        rows = self.conn.execute(MONTHLY_RUNNING_TOTAL).fetchall()
        return [{"month": m, "month_total_minor": t,
                 "running_total_minor": r} for m, t, r in rows]

    def yoy_growth(self) -> list[dict]:
        rows = self.conn.execute(YOY_GROWTH).fetchall()
        return [{"month": m, "month_total_minor": t,
                 "prior_month_total_minor": p,
                 "growth_pct": g} for m, t, p, g in rows]

    def segment_rank(self) -> list[dict]:
        rows = self.conn.execute(SEGMENT_RANK).fetchall()
        return [{"segment": s, "total_minor": t, "revenue_rank": r}
                for s, t, r in rows]

    def unrecognised_billings(self) -> list[dict]:
        rows = self.conn.execute(UNRECOGNISED_BILLINGS).fetchall()
        return [{"invoice_id": i, "month": m, "segment": s,
                 "unrecognised_minor": u} for i, m, s, u in rows]

    def close_status(self) -> list[dict]:
        rows = self.conn.execute(CLOSE_STATUS).fetchall()
        return [{"month": m, "tasks": t, "tasks_done": d,
                 "pct_done": p} for m, t, d, p in rows]
