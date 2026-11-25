"""D1-style durable store: a managed SQLite database.

Mirrors the Cloudflare D1 idea in Python: a small relational store with
versioned migrations, parameterized queries only (no string-built SQL),
explicit transactions, and per-query timing recorded for monitoring.
SQLite is used here exactly as D1 uses it under the hood.
"""

import sqlite3
import time
from pathlib import Path


class StoreError(Exception):
    """Raised for store-level failures (bad migration, bad query)."""


class DurableStore:
    """A SQLite-backed relational store with migrations and timed queries."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.query_log: list[dict] = []
        self._migrate()

    def _migrate(self) -> None:
        """Apply versioned migrations in order; record the applied version."""
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations"
            " (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
        )
        applied = {r[0] for r in self.conn.execute("SELECT version FROM _migrations")}
        migrations = {
            1: (
                "CREATE TABLE IF NOT EXISTS users ("
                " id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,"
                " name TEXT NOT NULL, created_at REAL NOT NULL)"
            ),
            2: (
                "CREATE TABLE IF NOT EXISTS events ("
                " id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),"
                " kind TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL,"
                " processed INTEGER NOT NULL DEFAULT 0)"
            ),
            3: "CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, created_at)",
        }
        for version in sorted(migrations):
            if version not in applied:
                self.conn.execute(migrations[version])
                self.conn.execute(
                    "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
                    (version, time.time()),
                )
        self.conn.commit()

    @property
    def schema_version(self) -> int:
        row = self.conn.execute("SELECT MAX(version) AS v FROM _migrations").fetchone()
        return int(row["v"] or 0)

    def execute(self, sql: str, params: tuple = ()) -> list[dict]:
        """Run one parameterized statement; SELECT returns rows, else rowcount."""
        started = time.perf_counter()
        try:
            cur = self.conn.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            self.conn.commit()
            return rows
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise StoreError(f"query failed: {exc}") from exc
        finally:
            self.query_log.append(
                {"sql": sql, "ms": round((time.perf_counter() - started) * 1000, 3)}
            )

    def execute_many(self, sql: str, rows: list[tuple]) -> int:
        """Run one parameterized statement over many rows in a single transaction."""
        started = time.perf_counter()
        try:
            cur = self.conn.executemany(sql, rows)
            self.conn.commit()
            return cur.rowcount
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise StoreError(f"batch insert failed: {exc}") from exc
        finally:
            self.query_log.append(
                {"sql": sql, "ms": round((time.perf_counter() - started) * 1000, 3)}
            )

    def transaction(self, statements: list[tuple[str, tuple]]) -> None:
        """Run several parameterized statements atomically; all or nothing."""
        try:
            for sql, params in statements:
                self.conn.execute(sql, params)
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise StoreError(f"transaction failed, rolled back: {exc}") from exc

    def create_user(self, email: str, name: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO users (email, name, created_at) VALUES (?, ?, ?)",
            (email, name, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def record_event(self, user_id: int, kind: str, payload: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO events (user_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
            (user_id, kind, payload, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def user_events(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, kind, payload, created_at FROM events"
            " WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def event_counts_by_kind(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT kind, COUNT(*) AS n FROM events GROUP BY kind ORDER BY n DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def slow_queries(self, threshold_ms: float = 5.0) -> list[dict]:
        return [q for q in self.query_log if q["ms"] >= threshold_ms]

    def close(self) -> None:
        self.conn.close()
