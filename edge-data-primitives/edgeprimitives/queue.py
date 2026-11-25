"""Queues-style messaging primitive: at-least-once delivery on SQLite.

Mirrors the Cloudflare Queues idea in Python: producers enqueue JSON
messages, consumers lease a batch (visibility timeout hides leased rows),
acknowledge on success, and failed messages are retried up to a limit and
then moved to a dead-letter queue instead of being lost or retried forever.
"""

import json
import sqlite3
import time
from pathlib import Path


class QueueError(Exception):
    """Raised for queue-level failures."""


class MessageQueue:
    """A durable FIFO-ish queue with leasing, retries, and a dead-letter queue."""

    def __init__(self, path: str | Path = ":memory:", max_attempts: int = 3):
        self.path = str(path)
        self.max_attempts = max_attempts
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            " id INTEGER PRIMARY KEY, body TEXT NOT NULL,"
            " attempts INTEGER NOT NULL DEFAULT 0,"
            " visible_at REAL NOT NULL, created_at REAL NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS dead_letter ("
            " id INTEGER PRIMARY KEY, body TEXT NOT NULL,"
            " attempts INTEGER NOT NULL, failed_at REAL NOT NULL,"
            " reason TEXT NOT NULL)"
        )
        self.conn.commit()

    def enqueue(self, body: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages (body, visible_at, created_at) VALUES (?, ?, ?)",
            (json.dumps(body), time.time(), time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def enqueue_many(self, bodies: list[dict]) -> list[int]:
        now = time.time()
        ids = []
        for body in bodies:
            cur = self.conn.execute(
                "INSERT INTO messages (body, visible_at, created_at) VALUES (?, ?, ?)",
                (json.dumps(body), now, now),
            )
            ids.append(int(cur.lastrowid))
        self.conn.commit()
        return ids

    def lease(self, batch_size: int = 10, visibility_timeout_s: float = 30.0) -> list[dict]:
        """Lease up to batch_size visible messages; leased rows hide until timeout."""
        now = time.time()
        rows = self.conn.execute(
            "SELECT id, body, attempts FROM messages"
            " WHERE visible_at <= ? ORDER BY id LIMIT ?",
            (now, batch_size),
        ).fetchall()
        leased = []
        for row in rows:
            self.conn.execute(
                "UPDATE messages SET visible_at = ? WHERE id = ?",
                (now + visibility_timeout_s, row["id"]),
            )
            leased.append(
                {"id": row["id"], "body": json.loads(row["body"]), "attempts": row["attempts"]}
            )
        self.conn.commit()
        return leased

    def ack(self, message_id: int) -> None:
        self.conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        self.conn.commit()

    def nack(self, message_id: int, reason: str) -> str:
        """Fail a leased message: retry later, or dead-letter after max attempts."""
        row = self.conn.execute(
            "SELECT body, attempts FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise QueueError(f"message {message_id} not found (already acked or dead)")
        attempts = int(row["attempts"]) + 1
        if attempts >= self.max_attempts:
            self.conn.execute(
                "INSERT INTO dead_letter (body, attempts, failed_at, reason)"
                " VALUES (?, ?, ?, ?)",
                (row["body"], attempts, time.time(), reason),
            )
            self.conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
            self.conn.commit()
            return "dead-lettered"
        self.conn.execute(
            "UPDATE messages SET attempts = ?, visible_at = ? WHERE id = ?",
            (attempts, time.time(), message_id),
        )
        self.conn.commit()
        return "retried"

    def depth(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    def dead_letter_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM dead_letter").fetchone()[0])

    def dead_letters(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, body, attempts, reason FROM dead_letter ORDER BY id"
        ).fetchall()
        return [
            {"id": r["id"], "body": json.loads(r["body"]), "attempts": r["attempts"], "reason": r["reason"]}
            for r in rows
        ]

    def close(self) -> None:
        self.conn.close()
