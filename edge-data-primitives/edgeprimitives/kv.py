"""Workers KV-style key-value store: global, low-latency, eventually consistent.

Mirrors the Cloudflare Workers KV idea in Python: keys with optional TTL
and metadata, prefix listing with cursor pagination, and a simulated
replica that lags behind the primary by a configurable delay, so reads
from the replica can briefly return stale values — the eventual-consistency
behaviour callers of a global KV must handle.
"""

import json
import sqlite3
import time
from pathlib import Path


class KVError(Exception):
    """Raised for KV-level failures."""


class KeyValueStore:
    """A TTL key-value store with metadata, prefix listing, and a lagging replica."""

    def __init__(self, path: str | Path = ":memory:", replica_lag_s: float = 0.0):
        self.path = str(path)
        self.replica_lag_s = replica_lag_s
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL,"
            " metadata TEXT, expires_at REAL, updated_at REAL NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS kv_replica ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL,"
            " metadata TEXT, expires_at REAL, updated_at REAL NOT NULL)"
        )
        self.conn.commit()

    def put(self, key: str, value: str, ttl_s: float | None = None, metadata: dict | None = None) -> None:
        if not key:
            raise KVError("key must not be empty")
        now = time.time()
        expires = now + ttl_s if ttl_s is not None else None
        meta = json.dumps(metadata) if metadata is not None else None
        self.conn.execute(
            "INSERT INTO kv (key, value, metadata, expires_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
            " metadata=excluded.metadata, expires_at=excluded.expires_at,"
            " updated_at=excluded.updated_at",
            (key, value, meta, expires, now),
        )
        self.conn.commit()

    def get(self, key: str, replica: bool = False) -> str | None:
        """Read from the primary, or from the replica (stale while lag applies)."""
        if replica:
            self._replicate()
        table = "kv_replica" if replica else "kv"
        row = self.conn.execute(
            f"SELECT value, expires_at FROM {table} WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] is not None and row["expires_at"] <= time.time():
            return None
        return row["value"]

    def get_with_metadata(self, key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT value, metadata, expires_at FROM kv WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] is not None and row["expires_at"] <= time.time():
            return None
        return {
            "value": row["value"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            "expires_at": row["expires_at"],
        }

    def delete(self, key: str) -> bool:
        cur = self.conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_keys(self, prefix: str = "", limit: int = 100, cursor: str | None = None) -> dict:
        """List live keys by prefix; cursor is the last key of the previous page."""
        now = time.time()
        if cursor is None:
            rows = self.conn.execute(
                "SELECT key FROM kv WHERE key LIKE ?"
                " AND (expires_at IS NULL OR expires_at > ?)"
                " ORDER BY key LIMIT ?",
                (prefix + "%", now, limit + 1),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT key FROM kv WHERE key LIKE ? AND key > ?"
                " AND (expires_at IS NULL OR expires_at > ?)"
                " ORDER BY key LIMIT ?",
                (prefix + "%", cursor, now, limit + 1),
            ).fetchall()
        keys = [r["key"] for r in rows]
        if len(keys) > limit:
            next_cursor = keys[limit - 1]
            keys = keys[:limit]
        else:
            next_cursor = None
        return {"keys": keys, "next_cursor": next_cursor}

    def purge_expired(self) -> int:
        cur = self.conn.execute(
            "DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (time.time(),),
        )
        self.conn.commit()
        return cur.rowcount

    def _replicate(self) -> None:
        """Copy primary rows older than the lag into the replica (eventual consistency)."""
        cutoff = time.time() - self.replica_lag_s
        self.conn.execute(
            "INSERT OR REPLACE INTO kv_replica (key, value, metadata, expires_at, updated_at)"
            " SELECT key, value, metadata, expires_at, updated_at FROM kv"
            " WHERE updated_at <= ?",
            (cutoff,),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
