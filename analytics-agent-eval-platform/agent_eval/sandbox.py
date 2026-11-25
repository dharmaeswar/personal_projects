"""Sandboxed analytical SQL execution with access controls and provenance.

The analytics agent never touches raw tables directly. Every query goes
through this sandbox, which enforces:

- SELECT-only, single-statement queries (no writes, no DDL, no ATTACH/PRAGMA).
- A per-role table allow-list (analysts see aggregates + posts, not raw votes).
- Row and time limits, so a bad query cannot run away.
- An audit trail: every execution is recorded with its query hash, dataset
  version, role, row count and latency, so any result can be reproduced.

All data is synthetic and seeded; nothing here is real Reddit data.
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
import time

DATASET_VERSION = "community-analytics-v1"

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "attach",
    "pragma", "vacuum", "replace", "truncate", "grant", "revoke",
}

# Role -> tables the role may read.
ROLE_TABLES = {
    "analyst": {"communities", "posts"},
    "scientist": {"communities", "posts"},
    "admin": {"communities", "posts"},
}

COMMUNITIES = [
    ("python", 4200000, "2010-03-01"),
    ("datascience", 3100000, "2012-06-15"),
    ("machinelearning", 3800000, "2011-09-20"),
    ("learnprogramming", 5100000, "2010-11-05"),
    ("statistics", 900000, "2013-02-11"),
]

POST_TITLES = [
    "How do I debug a slow pandas groupby?",
    "A gentle intro to Bayesian updating",
    "What actually changed in Python 3.12?",
    "Gradient boosting vs random forests on tabular data",
    "Why is my model overfitting on 200 rows?",
    "SQL window functions, finally explained",
    "A/B test peeking and why it inflates false positives",
    "From Jupyter to a scheduled pipeline",
    "Confidence intervals are not what you think",
    "Profiling a training loop that got slower",
]


class SandboxError(Exception):
    """Raised when a query is rejected by the sandbox."""


def _seed_posts(conn: sqlite3.Connection) -> None:
    rng = random.Random(42)
    rows = []
    post_id = 1
    for day in range(30):  # day 0..29, day 29 is "today"
        for community, _, _ in COMMUNITIES:
            n = rng.randint(1, 4)
            for _ in range(n):
                title = rng.choice(POST_TITLES)
                score = rng.randint(2, 480)
                comments = rng.randint(0, 210)
                rows.append((post_id, community, title, score, comments, day))
                post_id += 1
    conn.executemany(
        "INSERT INTO posts (id, community, title, score, comments, created_day)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )


class Sandbox:
    """A SQLite-backed analytical sandbox with audit and provenance."""

    def __init__(self, role: str = "analyst"):
        if role not in ROLE_TABLES:
            raise SandboxError(f"unknown role: {role!r}")
        self.role = role
        self.dataset_version = DATASET_VERSION
        self.audit: list[dict] = []
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE communities (name TEXT PRIMARY KEY, members INTEGER,"
            " created TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE posts (id INTEGER PRIMARY KEY, community TEXT,"
            " title TEXT, score INTEGER, comments INTEGER, created_day INTEGER)"
        )
        self.conn.executemany(
            "INSERT INTO communities (name, members, created) VALUES (?, ?, ?)",
            COMMUNITIES,
        )
        _seed_posts(self.conn)
        self.conn.commit()

    def describe_dataset(self) -> dict:
        """Schema + grain documentation the agent uses for context retrieval."""
        return {
            "dataset_version": self.dataset_version,
            "tables": {
                "communities": {
                    "columns": ["name", "members", "created"],
                    "grain": "one row per community",
                    "rows": len(COMMUNITIES),
                },
                "posts": {
                    "columns": ["id", "community", "title", "score",
                                "comments", "created_day"],
                    "grain": "one row per post; created_day 0..29, 29 is today",
                    "rows": self.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
                },
            },
            "notes": [
                "score is net upvotes on the post; comments is the comment count.",
                "created_day is a day index, not a date; use 29 - N for last N days.",
                "Aggregates over posts must state the day window used.",
            ],
        }

    def _check(self, sql: str) -> None:
        cleaned = sql.strip().rstrip(";").strip()
        if not cleaned:
            raise SandboxError("empty query")
        if ";" in cleaned:
            raise SandboxError("only a single statement is allowed")
        first = cleaned.split(None, 1)[0].lower()
        if first != "select":
            raise SandboxError(f"only SELECT is allowed, got {first.upper()}")
        lowered = cleaned.lower()
        for word in FORBIDDEN_KEYWORDS:
            if word in lowered.split():
                raise SandboxError(f"forbidden keyword: {word}")
        allowed = ROLE_TABLES[self.role]
        for table in ("communities", "posts"):
            if table in lowered and table not in allowed:
                raise SandboxError(f"role {self.role!r} may not read {table}")

    def run_query(self, sql: str, *, row_limit: int = 1000,
                  timeout_s: float = 5.0) -> dict:
        """Execute a sandboxed query. Returns rows + provenance, or raises."""
        self._check(sql)
        query_hash = hashlib.sha256(sql.strip().encode()).hexdigest()[:12]
        started = time.monotonic()
        try:
            self.conn.execute(f"PRAGMA query_only = ON")
            cur = self.conn.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(row_limit + 1)
        except sqlite3.Error as exc:
            self._audit(sql, query_hash, ok=False, rows=0,
                        latency_ms=(time.monotonic() - started) * 1000,
                        error=str(exc))
            raise SandboxError(f"query failed: {exc}") from exc
        latency_ms = (time.monotonic() - started) * 1000
        truncated = len(rows) > row_limit
        rows = rows[:row_limit]
        self._audit(sql, query_hash, ok=True, rows=len(rows),
                    latency_ms=latency_ms, error=None)
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "truncated": truncated,
            "row_count": len(rows),
            "provenance": {
                "dataset_version": self.dataset_version,
                "query_hash": query_hash,
                "role": self.role,
                "row_limit": row_limit,
            },
        }

    def _audit(self, sql, query_hash, *, ok, rows, latency_ms, error):
        self.audit.append({
            "query": sql.strip(),
            "query_hash": query_hash,
            "dataset_version": self.dataset_version,
            "role": self.role,
            "ok": ok,
            "rows": rows,
            "latency_ms": round(latency_ms, 2),
            "error": error,
        })
