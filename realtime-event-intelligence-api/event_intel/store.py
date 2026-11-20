"""SQLite store for events and alerts, with fingerprint dedupe.

Every event gets a fingerprint from its source id, normalized text and
event type. A repeat of the same fingerprint is dropped and counted as
a duplicate instead of stored twice. Alerts are created only for
events whose severity score reaches the watch threshold.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time


def fingerprint(source_id: str, event_type: str, text: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    raw = f"{source_id}|{event_type}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class EventStore:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE NOT NULL,
                source_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                text TEXT NOT NULL,
                score REAL NOT NULL,
                band TEXT NOT NULL,
                received_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id),
                severity REAL NOT NULL,
                band TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        self.duplicates_dropped = 0

    def ingest(
        self,
        source_id: str,
        event_type: str,
        text: str,
        score: float,
        band_name: str,
        watch_threshold: float = 40.0,
    ) -> dict:
        """Store one scored event; returns its status and ids.

        Status is "stored", "duplicate", or "stored" with an alert id
        when the score reaches the watch threshold.
        """
        fp = fingerprint(source_id, event_type, text)
        cur = self.conn.execute(
            "SELECT id FROM events WHERE fingerprint = ?", (fp,)
        )
        if cur.fetchone() is not None:
            self.duplicates_dropped += 1
            return {"status": "duplicate", "fingerprint": fp}
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO events (fingerprint, source_id, event_type, text, score, band, received_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fp, source_id, event_type, text, score, band_name, now),
        )
        event_id = cur.lastrowid
        alert_id = None
        if score >= watch_threshold:
            cur = self.conn.execute(
                "INSERT INTO alerts (event_id, severity, band, created_at)"
                " VALUES (?, ?, ?, ?)",
                (event_id, score, band_name, now),
            )
            alert_id = cur.lastrowid
        self.conn.commit()
        return {
            "status": "stored",
            "event_id": event_id,
            "alert_id": alert_id,
            "fingerprint": fp,
        }

    def list_alerts(self, min_severity: float = 0.0) -> list[dict]:
        rows = self.conn.execute(
            "SELECT a.id AS alert_id, a.severity, a.band, e.id AS event_id,"
            " e.source_id, e.event_type, e.text"
            " FROM alerts a JOIN events e ON e.id = a.event_id"
            " WHERE a.severity >= ? ORDER BY a.severity DESC, a.id ASC",
            (min_severity,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_alert(self, alert_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT a.id AS alert_id, a.severity, a.band, e.id AS event_id,"
            " e.source_id, e.event_type, e.text"
            " FROM alerts a JOIN events e ON e.id = a.event_id WHERE a.id = ?",
            (alert_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def counts(self) -> dict:
        events = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        alerts = self.conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        return {
            "events": events,
            "alerts": alerts,
            "duplicates_dropped": self.duplicates_dropped,
        }
