"""SQLite store for LLM training-data infrastructure.

Tables:
  datasets        - registered datasets (name, modality, owner, description)
  dataset_versions- immutable versions of a dataset (version, row count, hash)
  records         - ingested records (content hash, modality, payload, quality)
  quality_checks  - quality-gate results per record batch
  lineage         - provenance edges (parent dataset/version -> child)
  ingestion_jobs  - batch/streaming ingestion runs with counts + status
  audit_log       - append-only record of state changes
All data is synthetic demo data; nothing here describes a real platform.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone


SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    modality TEXT NOT NULL,
    owner TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    version TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(dataset_id, version)
);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    modality TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'accepted',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_hash ON records(content_hash);
CREATE TABLE IF NOT EXISTS quality_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    version TEXT NOT NULL,
    check_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    parent_version TEXT NOT NULL,
    child_dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    child_version TEXT NOT NULL,
    transform TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    version TEXT NOT NULL,
    kind TEXT NOT NULL,
    received INTEGER NOT NULL,
    accepted INTEGER NOT NULL,
    duplicates INTEGER NOT NULL,
    quarantined INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class Store:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def _insert(self, sql: str, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur.lastrowid

    def audit(self, entity: str, entity_id: int, action: str, detail: str = ""):
        self._insert(
            "INSERT INTO audit_log (entity, entity_id, action, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (entity, entity_id, action, detail, now_iso()),
        )

    # -- datasets --------------------------------------------------------
    def create_dataset(self, name: str, modality: str, owner: str, description: str = "") -> int:
        if not name.strip():
            raise ValueError("dataset name must not be empty")
        try:
            ds_id = self._insert(
                "INSERT INTO datasets (name, modality, owner, description, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, modality, owner, description, now_iso()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"dataset '{name}' already exists") from exc
        self.audit("dataset", ds_id, "created", name)
        return ds_id

    def get_dataset(self, ds_id: int):
        row = self.conn.execute("SELECT * FROM datasets WHERE id = ?", (ds_id,)).fetchone()
        return dict(row) if row else None

    def list_datasets(self, modality: str | None = None):
        sql = "SELECT * FROM datasets"
        params: tuple = ()
        if modality:
            sql += " WHERE modality = ?"
            params = (modality,)
        rows = self.conn.execute(sql + " ORDER BY created_at", params).fetchall()
        return [dict(r) for r in rows]

    def search_datasets(self, query: str):
        like = f"%{query}%"
        rows = self.conn.execute(
            "SELECT * FROM datasets WHERE name LIKE ? OR description LIKE ? ORDER BY created_at",
            (like, like),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- versions -----------------------------------------------------------
    def create_version(self, dataset_id: int, version: str) -> int:
        if self.get_dataset(dataset_id) is None:
            raise ValueError(f"unknown dataset id {dataset_id}")
        try:
            ver_id = self._insert(
                "INSERT INTO dataset_versions (dataset_id, version, created_at)"
                " VALUES (?, ?, ?)",
                (dataset_id, version, now_iso()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"version '{version}' already exists for dataset {dataset_id}") from exc
        self.audit("dataset_version", ver_id, "created", version)
        return ver_id

    def list_versions(self, dataset_id: int):
        rows = self.conn.execute(
            "SELECT * FROM dataset_versions WHERE dataset_id = ? ORDER BY created_at",
            (dataset_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- records -------------------------------------------------------------
    def insert_record(self, dataset_id: int, version: str, payload: dict, modality: str) -> int | None:
        """Insert a record; returns None when the content hash already exists
        in this dataset version (duplicate)."""
        ch = content_hash(payload)
        existing = self.conn.execute(
            "SELECT id FROM records WHERE dataset_id = ? AND version = ? AND content_hash = ?",
            (dataset_id, version, ch),
        ).fetchone()
        if existing:
            return None
        rec_id = self._insert(
            "INSERT INTO records (dataset_id, version, content_hash, modality, payload_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (dataset_id, version, ch, modality, json.dumps(payload), now_iso()),
        )
        return rec_id

    def set_record_status(self, rec_id: int, status: str):
        cur = self.conn.execute(
            "UPDATE records SET status = ? WHERE id = ?", (status, rec_id)
        )
        if cur.rowcount == 0:
            raise ValueError(f"unknown record id {rec_id}")
        self.conn.commit()

    def list_records(self, dataset_id: int, version: str | None = None, status: str | None = None):
        sql = "SELECT * FROM records WHERE dataset_id = ?"
        params: list = [dataset_id]
        if version:
            sql += " AND version = ?"
            params.append(version)
        if status:
            sql += " AND status = ?"
            params.append(status)
        rows = self.conn.execute(sql + " ORDER BY created_at", params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json"))
            out.append(d)
        return out

    # -- quality / lineage / jobs ---------------------------------------------
    def record_quality_check(self, dataset_id: int, version: str, name: str,
                             passed: int, failed: int, detail: str = "") -> int:
        return self._insert(
            "INSERT INTO quality_checks (dataset_id, version, check_name, passed, failed, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (dataset_id, version, name, passed, failed, detail, now_iso()),
        )

    def list_quality_checks(self, dataset_id: int):
        rows = self.conn.execute(
            "SELECT * FROM quality_checks WHERE dataset_id = ? ORDER BY created_at",
            (dataset_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_lineage(self, parent_id: int, parent_version: str,
                    child_id: int, child_version: str, transform: str) -> int:
        return self._insert(
            "INSERT INTO lineage (parent_dataset_id, parent_version, child_dataset_id, child_version, transform, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (parent_id, parent_version, child_id, child_version, transform, now_iso()),
        )

    def list_lineage(self, dataset_id: int):
        rows = self.conn.execute(
            "SELECT * FROM lineage WHERE parent_dataset_id = ? OR child_dataset_id = ? ORDER BY created_at",
            (dataset_id, dataset_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def record_ingestion_job(self, dataset_id: int, version: str, kind: str,
                             received: int, accepted: int, duplicates: int,
                             quarantined: int, status: str = "complete") -> int:
        return self._insert(
            "INSERT INTO ingestion_jobs (dataset_id, version, kind, received, accepted, duplicates, quarantined, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dataset_id, version, kind, received, accepted, duplicates, quarantined, status, now_iso()),
        )

    def list_ingestion_jobs(self, dataset_id: int | None = None):
        sql = "SELECT * FROM ingestion_jobs"
        params: tuple = ()
        if dataset_id is not None:
            sql += " WHERE dataset_id = ?"
            params = (dataset_id,)
        rows = self.conn.execute(sql + " ORDER BY created_at", params).fetchall()
        return [dict(r) for r in rows]

    def audit_entries(self, entity: str | None = None):
        sql = "SELECT * FROM audit_log"
        params: tuple = ()
        if entity:
            sql += " WHERE entity = ?"
            params = (entity,)
        rows = self.conn.execute(sql + " ORDER BY id", params).fetchall()
        return [dict(r) for r in rows]
