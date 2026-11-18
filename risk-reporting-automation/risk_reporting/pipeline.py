"""SQLite pipeline: load synthetic data, run limit + stress checks in SQL.

Limit utilisation is computed twice — once in Python (limits.py) and
once in SQL — and the runner reconciles the two, so a mismatch is
caught instead of reported.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .data import Limit, Position
from .limits import LimitResult, status_for, utilisation
from .stress import StressResult


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS positions;
        DROP TABLE IF EXISTS limits;
        DROP TABLE IF EXISTS limit_results;
        DROP TABLE IF EXISTS stress_results;
        CREATE TABLE positions (
            trade_id TEXT PRIMARY KEY,
            desk TEXT NOT NULL,
            risk_type TEXT NOT NULL,
            exposure_usd REAL NOT NULL,
            notional_usd REAL NOT NULL,
            currency TEXT NOT NULL,
            as_of_date TEXT NOT NULL
        );
        CREATE TABLE limits (
            desk TEXT NOT NULL,
            risk_type TEXT NOT NULL,
            limit_usd REAL NOT NULL,
            warning_pct REAL NOT NULL,
            PRIMARY KEY (desk, risk_type)
        );
        CREATE TABLE limit_results (
            desk TEXT NOT NULL,
            risk_type TEXT NOT NULL,
            exposure_usd REAL NOT NULL,
            limit_usd REAL NOT NULL,
            utilisation REAL NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (desk, risk_type)
        );
        CREATE TABLE stress_results (
            scenario TEXT PRIMARY KEY,
            liquid_assets REAL NOT NULL,
            stressed_outflows REAL NOT NULL,
            coverage_ratio REAL NOT NULL,
            status TEXT NOT NULL
        );
        """
    )
    conn.commit()


def load_data(conn: sqlite3.Connection, positions: list[Position],
              limits: list[Limit]) -> None:
    conn.executemany(
        "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(p.trade_id, p.desk, p.risk_type, p.exposure_usd, p.notional_usd,
          p.currency, p.as_of_date) for p in positions],
    )
    conn.executemany(
        "INSERT INTO limits VALUES (?, ?, ?, ?)",
        [(l.desk, l.risk_type, l.limit_usd, l.warning_pct) for l in limits],
    )
    conn.commit()


def sql_limit_results(conn: sqlite3.Connection) -> list[LimitResult]:
    """Aggregate exposures and utilisation with a real SQL GROUP BY.

    Invalid rows (negative exposure) and rows with no matching limit
    are excluded in SQL, mirroring the Python aggregation.
    """
    rows = conn.execute(
        """
        SELECT l.desk, l.risk_type,
               COALESCE(SUM(p.exposure_usd), 0.0) AS exposure_usd,
               l.limit_usd
        FROM limits l
        LEFT JOIN positions p
          ON p.desk = l.desk AND p.risk_type = l.risk_type
         AND p.exposure_usd >= 0
        GROUP BY l.desk, l.risk_type
        ORDER BY l.desk, l.risk_type
        """
    ).fetchall()
    results = []
    for row in rows:
        util = utilisation(row["exposure_usd"], row["limit_usd"])
        results.append(
            LimitResult(row["desk"], row["risk_type"],
                        round(row["exposure_usd"], 2), row["limit_usd"],
                        round(util, 4), status_for(util))
        )
    return results


def store_results(conn: sqlite3.Connection, limit_results: list[LimitResult],
                  stress_results: list[StressResult]) -> None:
    conn.executemany(
        "INSERT INTO limit_results VALUES (?, ?, ?, ?, ?, ?)",
        [(r.desk, r.risk_type, r.exposure_usd, r.limit_usd,
          r.utilisation, r.status) for r in limit_results],
    )
    conn.executemany(
        "INSERT INTO stress_results VALUES (?, ?, ?, ?, ?)",
        [(s.scenario, s.liquid_assets, s.stressed_outflows,
          s.coverage_ratio, s.status) for s in stress_results],
    )
    conn.commit()


def reconcile(python_results: list[LimitResult],
              sql_results: list[LimitResult]) -> list[str]:
    """Return a list of mismatches between the Python and SQL aggregates."""
    sql_map = {(r.desk, r.risk_type): r for r in sql_results}
    mismatches = []
    for r in python_results:
        s = sql_map.get((r.desk, r.risk_type))
        if s is None:
            mismatches.append(f"missing SQL result for {r.desk}/{r.risk_type}")
        elif abs(s.exposure_usd - r.exposure_usd) > 0.01 or s.status != r.status:
            mismatches.append(
                f"{r.desk}/{r.risk_type}: python {r.exposure_usd} "
                f"({r.status}) vs SQL {s.exposure_usd} ({s.status})"
            )
    return mismatches
