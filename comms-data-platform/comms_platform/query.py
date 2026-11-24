"""Query serving — a local model of Athena over the gold layer.

Gold tables are loaded into an in-memory SQLite database and served through
read-only SQL. Only SELECT (and WITH ... SELECT) statements are accepted;
anything else is rejected before it runs, the way a read-only Athena
workgroup would enforce it.
"""

from __future__ import annotations

import sqlite3

import pandas as pd


class UnsafeQuery(ValueError):
    pass


def _guard(sql):
    stripped = sql.strip().rstrip(";")
    first = stripped.split(None, 1)[0].upper() if stripped.split() else ""
    if first == "WITH":
        body = stripped[4:].strip().upper()
        if "SELECT" not in body:
            raise UnsafeQuery("only SELECT queries are allowed")
    elif first != "SELECT":
        raise UnsafeQuery("only SELECT queries are allowed")
    banned = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "PRAGMA", "ATTACH"]
    upper = stripped.upper()
    for word in banned:
        if word in upper:
            raise UnsafeQuery(f"forbidden keyword in query: {word}")


class QueryEngine:
    """Athena-style read-only SQL over gold tables held in SQLite."""

    def __init__(self, tables):
        """`tables`: mapping of table name -> pandas DataFrame."""
        self.conn = sqlite3.connect(":memory:")
        for name, df in tables.items():
            df.to_sql(name, self.conn, index=False, if_exists="replace")

    def query(self, sql):
        _guard(sql)
        cur = self.conn.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def close(self):
        self.conn.close()
