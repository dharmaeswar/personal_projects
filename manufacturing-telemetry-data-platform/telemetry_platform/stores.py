"""Multi-store data abstraction.

One write path fans telemetry out to four stores behind a single
interface, the way a data platform abstracts its storage technologies:

- ``TimeSeriesStore`` — append-only measurements (InfluxDB-style).
- ``DocumentStore`` — machine configuration documents (MongoDB-style).
- ``CacheStore`` — latest reading per machine with TTL (Redis-style).
- ``RelationalStore`` — runs, layers and weld jobs (PostgreSQL-style).

SQLite backs the time-series and relational stores; documents and the
cache live in memory. Nothing here claims a real cluster: the point is
the abstraction and the routing, which map one-to-one onto the real
stores named in the docstrings.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryReading:
    machine_id: str
    ts: int  # epoch seconds
    temp_c: float
    vibration_mm_s: float
    weld_current_a: float
    layer: int
    status: str


class TimeSeriesStore:
    """Append-only measurements, indexed by machine and time."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS measurements"
            " (machine_id TEXT, ts INTEGER, temp_c REAL,"
            "  vibration_mm_s REAL, weld_current_a REAL, layer INTEGER,"
            "  status TEXT)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_measurements_machine_ts"
            " ON measurements (machine_id, ts)"
        )
        conn.commit()

    def write(self, reading: TelemetryReading) -> None:
        self._conn.execute(
            "INSERT INTO measurements VALUES (?,?,?,?,?,?,?)",
            (reading.machine_id, reading.ts, reading.temp_c,
             reading.vibration_mm_s, reading.weld_current_a,
             reading.layer, reading.status),
        )
        self._conn.commit()

    def range(self, machine_id: str, start: int, end: int) -> list[TelemetryReading]:
        rows = self._conn.execute(
            "SELECT machine_id, ts, temp_c, vibration_mm_s, weld_current_a,"
            " layer, status FROM measurements"
            " WHERE machine_id = ? AND ts BETWEEN ? AND ? ORDER BY ts",
            (machine_id, start, end),
        ).fetchall()
        return [TelemetryReading(*row) for row in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]


class DocumentStore:
    """Machine configuration documents, keyed by machine id."""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def put(self, machine_id: str, document: dict) -> None:
        self._docs[machine_id] = dict(document)

    def get(self, machine_id: str) -> dict | None:
        doc = self._docs.get(machine_id)
        return dict(doc) if doc is not None else None

    def find_by_type(self, machine_type: str) -> list[str]:
        return sorted(
            mid for mid, doc in self._docs.items()
            if doc.get("type") == machine_type
        )


class CacheStore:
    """Latest reading per machine, with a TTL in seconds."""

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, dict]] = {}

    def set(self, machine_id: str, value: dict) -> None:
        self._cache[machine_id] = (time.time(), dict(value))

    def get(self, machine_id: str) -> dict | None:
        entry = self._cache.get(machine_id)
        if entry is None:
            return None
        stored_at, value = entry
        if time.time() - stored_at > self._ttl:
            del self._cache[machine_id]
            return None
        return dict(value)


class RelationalStore:
    """Runs and weld jobs: the relational side of the platform."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runs"
            " (run_id TEXT PRIMARY KEY, machine_id TEXT,"
            "  started_ts INTEGER, part TEXT, layers_planned INTEGER)"
        )
        conn.commit()

    def start_run(self, run_id: str, machine_id: str, started_ts: int,
                  part: str, layers_planned: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
            (run_id, machine_id, started_ts, part, layers_planned),
        )
        self._conn.commit()

    def runs_for_machine(self, machine_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT run_id, machine_id, started_ts, part, layers_planned"
            " FROM runs WHERE machine_id = ? ORDER BY started_ts",
            (machine_id,),
        ).fetchall()
        return [dict(zip(
            ("run_id", "machine_id", "started_ts", "part", "layers_planned"),
            row)) for row in rows]


class DataPlatform:
    """One write path, four stores: the platform facade."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self.timeseries = TimeSeriesStore(self._conn)
        self.documents = DocumentStore()
        self.cache = CacheStore()
        self.relational = RelationalStore(self._conn)

    def ingest(self, reading: TelemetryReading) -> None:
        """Route one reading to every store that needs it."""
        self.timeseries.write(reading)
        self.cache.set(reading.machine_id, {
            "ts": reading.ts, "temp_c": reading.temp_c,
            "vibration_mm_s": reading.vibration_mm_s,
            "weld_current_a": reading.weld_current_a,
            "layer": reading.layer, "status": reading.status,
        })

    def register_machine(self, machine_id: str, document: dict) -> None:
        self.documents.put(machine_id, document)

    def close(self) -> None:
        self._conn.close()
