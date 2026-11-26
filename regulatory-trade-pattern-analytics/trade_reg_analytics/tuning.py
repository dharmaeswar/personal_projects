"""SQL query tuning for the trade-regulation warehouse.

The analytics queries in this toolkit run against the orders, trades and
positions tables. This module measures them the way a data-analytics
developer would on a real warehouse: EXPLAIN QUERY PLAN to see whether
a query scans or seeks, wall-clock timing before and after indexing,
and a short tuning report with the evidence.

All data is synthetic and seeded (see ``data.py``); the timings are
demo-scale, not production benchmarks.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import time
from pathlib import Path

# Candidate indexes for the warehouse. The positions table already has
# a primary key on (account, instrument, trade_date), so only the
# date-led lookup needs a new index there.
RECOMMENDED_INDEXES: list[tuple[str, str]] = [
    (
        "idx_orders_account_date",
        "CREATE INDEX IF NOT EXISTS idx_orders_account_date "
        "ON orders (account, trade_date, instrument)",
    ),
    (
        "idx_orders_instrument_date",
        "CREATE INDEX IF NOT EXISTS idx_orders_instrument_date "
        "ON orders (instrument, trade_date)",
    ),
    (
        "idx_trades_account_date",
        "CREATE INDEX IF NOT EXISTS idx_trades_account_date "
        "ON trades (account, trade_date)",
    ),
    (
        "idx_trades_date_instrument",
        "CREATE INDEX IF NOT EXISTS idx_trades_date_instrument "
        "ON trades (trade_date, instrument)",
    ),
    (
        "idx_trades_wash_join",
        "CREATE INDEX IF NOT EXISTS idx_trades_wash_join "
        "ON trades (account, instrument, trade_date, side, quantity)",
    ),
    (
        "idx_orders_status_cancel",
        "CREATE INDEX IF NOT EXISTS idx_orders_status_cancel "
        "ON orders (status, cancel_seconds, account, instrument)",
    ),
    (
        "idx_positions_date_account",
        "CREATE INDEX IF NOT EXISTS idx_positions_date_account "
        "ON positions (trade_date, account)",
    ),
]

# The recurring analytics queries, with the parameters a daily run uses.
# ``repeats`` bounds the timing loop: the wash-trade self-join is the
# most expensive query, so it is timed fewer times.
ANALYTICS_QUERIES: dict[str, dict] = {
    "daily_volume_by_instrument": {
        "sql": (
            "SELECT trade_date, instrument, COUNT(*), SUM(quantity) "
            "FROM trades WHERE trade_date BETWEEN ? AND ? "
            "GROUP BY trade_date, instrument"
        ),
        "params": ("2026-10-26", "2026-11-20"),
        "repeats": 5,
        "description": "Daily traded volume and quantity per instrument.",
    },
    "account_volume_share": {
        "sql": (
            "SELECT account, SUM(quantity) AS qty FROM trades "
            "WHERE trade_date = ? GROUP BY account ORDER BY qty DESC LIMIT 10"
        ),
        "params": ("2026-11-20",),
        "repeats": 5,
        "description": "Top accounts by traded quantity on one day.",
    },
    "wash_trade_candidates": {
        "sql": (
            "SELECT a.trade_id, b.trade_id, a.account, a.instrument, a.quantity "
            "FROM trades a JOIN trades b "
            "ON a.account = b.account AND a.instrument = b.instrument "
            "AND a.trade_date = b.trade_date AND a.quantity = b.quantity "
            "AND a.side = 'BUY' AND b.side = 'SELL' AND a.trade_id < b.trade_id "
            "WHERE a.trade_date = ?"
        ),
        "params": ("2026-11-20",),
        "repeats": 3,
        "description": "Matched buy/sell pairs, same account and day (wash-trade triage).",
    },
    "fast_cancel_scan": {
        "sql": (
            "SELECT account, instrument, COUNT(*) AS n FROM orders "
            "WHERE status = 'CANCELLED' AND cancel_seconds <= 10 "
            "GROUP BY account, instrument ORDER BY n DESC LIMIT 10"
        ),
        "params": (),
        "repeats": 5,
        "description": "Accounts cancelling large orders within 10 seconds (spoofing triage).",
    },
    "position_concentration": {
        "sql": (
            "SELECT account, instrument, SUM(net_quantity) AS net FROM positions "
            "WHERE trade_date = ? GROUP BY account, instrument ORDER BY ABS(net) DESC LIMIT 10"
        ),
        "params": ("2026-11-20",),
        "repeats": 5,
        "description": "Largest net positions per account and instrument on one day.",
    },
}


def explain_plan(
    conn: sqlite3.Connection, sql: str, params: tuple = ()
) -> list[dict]:
    """Return the EXPLAIN QUERY PLAN rows for a query as dicts."""
    rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return [
        {"id": r[0], "parent": r[1], "notused": r[2], "detail": r[3]} for r in rows
    ]


def uses_full_scan(plan: list[dict]) -> bool:
    """True when any plan step scans a whole table instead of seeking."""
    return any("SCAN" in step["detail"] for step in plan)


def plan_summary(plan: list[dict]) -> str:
    """One-line summary of a query plan, for reports."""
    return "; ".join(step["detail"] for step in plan)


def time_query(
    conn: sqlite3.Connection, sql: str, params: tuple = (), repeats: int = 5
) -> float:
    """Median wall-clock time in milliseconds for one query."""
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        conn.execute(sql, params).fetchall()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def existing_indexes(conn: sqlite3.Connection) -> set[str]:
    """Names of the indexes currently on the warehouse tables."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def apply_indexes(conn: sqlite3.Connection) -> list[str]:
    """Create the recommended indexes; return the names actually created."""
    before = existing_indexes(conn)
    for _, ddl in RECOMMENDED_INDEXES:
        conn.execute(ddl)
    conn.commit()
    return sorted(existing_indexes(conn) - before)


def tune_query(
    conn: sqlite3.Connection, name: str, spec: dict
) -> dict:
    """Tune one analytics query: plan and timing before and after indexing.

    Indexes are applied once (the first call creates them; later calls
    find them already in place), so ``*_after`` shows the indexed plan.
    """
    sql, params, repeats = spec["sql"], spec["params"], spec["repeats"]
    plan_before = explain_plan(conn, sql, params)
    ms_before = time_query(conn, sql, params, repeats)
    created = apply_indexes(conn)
    plan_after = explain_plan(conn, sql, params)
    ms_after = time_query(conn, sql, params, repeats)
    return {
        "name": name,
        "description": spec["description"],
        "sql": sql,
        "full_scan_before": uses_full_scan(plan_before),
        "plan_before": plan_summary(plan_before),
        "median_ms_before": round(ms_before, 3),
        "indexes_created": created,
        "full_scan_after": uses_full_scan(plan_after),
        "plan_after": plan_summary(plan_after),
        "median_ms_after": round(ms_after, 3),
        "speedup": round(ms_before / ms_after, 2) if ms_after > 0 else None,
    }


def run_tuning(conn: sqlite3.Connection, out_dir: str | Path) -> dict:
    """Tune every analytics query and write the tuning report.

    Two phases, so the "before" numbers are honest: first measure
    every query on the unindexed warehouse, then apply the indexes
    once, then measure every query again. (Measuring one query at a
    time would let the first query's indexes leak into the next
    query's "before" numbers.)

    Returns the summary dict; also writes ``tuning_report.md`` and
    ``tuning_summary.json`` into ``out_dir``.
    """
    before = []
    for name, spec in ANALYTICS_QUERIES.items():
        plan = explain_plan(conn, spec["sql"], spec["params"])
        before.append(
            {
                "name": name,
                "full_scan": uses_full_scan(plan),
                "plan": plan_summary(plan),
                "median_ms": round(
                    time_query(conn, spec["sql"], spec["params"], spec["repeats"]), 3
                ),
            }
        )
    created = apply_indexes(conn)
    results = []
    for spec_before, (name, spec) in zip(before, ANALYTICS_QUERIES.items()):
        plan = explain_plan(conn, spec["sql"], spec["params"])
        ms_after = round(
            time_query(conn, spec["sql"], spec["params"], spec["repeats"]), 3
        )
        results.append(
            {
                "name": name,
                "description": spec["description"],
                "sql": spec["sql"],
                "full_scan_before": spec_before["full_scan"],
                "plan_before": spec_before["plan"],
                "median_ms_before": spec_before["median_ms"],
                "indexes_created": created,
                "full_scan_after": uses_full_scan(plan),
                "plan_after": plan_summary(plan),
                "median_ms_after": ms_after,
                "speedup": round(spec_before["median_ms"] / ms_after, 2)
                if ms_after > 0
                else None,
            }
        )
    improved = sum(1 for r in results if r["full_scan_before"] and not r["full_scan_after"])
    summary = {
        "queries_tuned": len(results),
        "full_scans_removed": improved,
        "results": results,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SQL Query Tuning Report",
        "",
        "Warehouse: orders / trades / positions (synthetic, seeded data).",
        f"Queries tuned: {len(results)}; full-table scans removed: {improved}.",
        "",
    ]
    for r in results:
        lines += [
            f"## {r['name']}",
            "",
            r["description"],
            "",
            f"- Plan before: {r['plan_before']}",
            f"- Full scan before: {r['full_scan_before']}",
            f"- Median time before: {r['median_ms_before']} ms",
            f"- Plan after: {r['plan_after']}",
            f"- Full scan after: {r['full_scan_after']}",
            f"- Median time after: {r['median_ms_after']} ms",
            f"- Speedup: {r['speedup']}x",
            "",
        ]
    (out / "tuning_report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "tuning_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
