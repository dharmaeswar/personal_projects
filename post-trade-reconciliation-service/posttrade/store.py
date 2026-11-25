"""Persistence: store enriched trades, breaks, positions and P&L.

The production store is PostgreSQL — see schema.sql for the DDL.
Local runs and tests use SQLite (Python standard library) as a
stand-in with the same tables and columns, so the service runs
anywhere without a database server.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS enriched_trades (
    exec_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    trade_date TEXT NOT NULL,
    venue TEXT NOT NULL,
    account TEXT NOT NULL,
    notional REAL NOT NULL,
    enriched INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    break_type TEXT NOT NULL,
    exec_id TEXT,
    clearing_id TEXT,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    account TEXT NOT NULL,
    symbol TEXT NOT NULL,
    net_quantity INTEGER NOT NULL,
    average_cost REAL NOT NULL,
    multiplier INTEGER NOT NULL,
    PRIMARY KEY (account, symbol)
);
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    account TEXT NOT NULL,
    symbol TEXT NOT NULL,
    realised REAL NOT NULL,
    unrealised REAL NOT NULL,
    net_quantity INTEGER NOT NULL,
    PRIMARY KEY (account, symbol)
);
"""


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open the store; in-memory when no path is given."""
    conn = sqlite3.connect(db_path or ":memory:")
    conn.executescript(SCHEMA)
    return conn


def save_run(conn, enriched, result, positions, pnl_rows) -> None:
    """Persist one full post-trade run (replaces prior snapshot rows)."""
    conn.execute("DELETE FROM enriched_trades")
    conn.execute("DELETE FROM breaks")
    conn.execute("DELETE FROM positions")
    conn.execute("DELETE FROM pnl_snapshots")
    for trade in enriched:
        exc = trade.execution
        conn.execute(
            "INSERT INTO enriched_trades VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                exc.exec_id,
                exc.symbol,
                exc.side,
                exc.quantity,
                exc.price,
                exc.trade_date,
                exc.venue,
                exc.account,
                trade.notional,
                1 if trade.enriched else 0,
            ),
        )
    for brk in result.breaks:
        conn.execute(
            "INSERT INTO breaks (break_type, exec_id, clearing_id, detail)"
            " VALUES (?,?,?,?)",
            (
                brk.break_type,
                brk.execution.exec_id if brk.execution else None,
                brk.clearing.clearing_id if brk.clearing else None,
                brk.detail,
            ),
        )
    for pos in positions:
        conn.execute(
            "INSERT INTO positions VALUES (?,?,?,?,?)",
            (pos.account, pos.symbol, pos.net_quantity, pos.average_cost, pos.multiplier),
        )
    for row in pnl_rows:
        conn.execute(
            "INSERT INTO pnl_snapshots VALUES (?,?,?,?,?)",
            (row.account, row.symbol, row.realised, row.unrealised, row.net_quantity),
        )
    conn.commit()


def load_positions(conn) -> list[dict]:
    """Read stored positions back as plain dicts."""
    cur = conn.execute(
        "SELECT account, symbol, net_quantity, average_cost, multiplier"
        " FROM positions ORDER BY account, symbol"
    )
    return [dict(zip(("account", "symbol", "net_quantity", "average_cost", "multiplier"), r)) for r in cur]


def load_breaks(conn) -> list[dict]:
    """Read stored breaks back as plain dicts."""
    cur = conn.execute(
        "SELECT break_type, exec_id, clearing_id, detail FROM breaks ORDER BY id"
    )
    return [dict(zip(("break_type", "exec_id", "clearing_id", "detail"), r)) for r in cur]


def load_pnl(conn) -> list[dict]:
    """Read stored P&L snapshots back as plain dicts."""
    cur = conn.execute(
        "SELECT account, symbol, realised, unrealised, net_quantity"
        " FROM pnl_snapshots ORDER BY account, symbol"
    )
    return [dict(zip(("account", "symbol", "realised", "unrealised", "net_quantity"), r)) for r in cur]
