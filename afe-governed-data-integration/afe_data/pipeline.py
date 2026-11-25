"""Pod pipeline: ingest -> contract -> transform -> quality -> govern -> publish.

Runs the full forward-deployed flow against a SQLite warehouse so a pod can
prove, locally, that a client feed is contract-clean, governed, and
retrievable before the same pattern is deployed into the client environment.
Idempotent: a re-run loads zero new rows (natural-key dedupe) and appends
no duplicate lineage.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import DataContract
from .governance import AccessControl, LineageEntry, LineageLog, classify_column
from .quality import check_rows, detect_schema_drift
from .retrieval import RetrievalIndex, feature_snapshot
from .sources import SourceAdapter
from .transform import transform_row


class PodPipeline:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.lineage = LineageLog()
        self.access = AccessControl()
        self.index = RetrievalIndex()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS positions (
                    position_id TEXT PRIMARY KEY,
                    client_id TEXT,
                    instrument TEXT,
                    notional REAL,
                    currency TEXT,
                    valuation_date TEXT,
                    source TEXT,
                    schema_version TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS quarantine (
                    record_id TEXT, reason TEXT, source TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS lineage (
                    record_id TEXT, source TEXT, schema_version TEXT,
                    transform TEXT, contract_version TEXT
                )"""
            )

    def run(self, adapter: SourceAdapter, contract: DataContract, reference_ids: set[str],
            previous_schema: list[str], age_hours: float = 1.0) -> dict:
        rows = adapter.read()
        payloads = [r.payload for r in rows]
        violations = contract.check(adapter.schema_seen, age_hours, payloads)
        drift = detect_schema_drift(adapter.profile.name, previous_schema, adapter.schema_seen)
        blocking_drift = [d for d in drift if d.blocking]
        if violations or blocking_drift:
            return {
                "loaded": 0,
                "quarantined": 0,
                "violations": [f"{v.kind}: {v.detail}" for v in violations],
                "drift": [f"{d.kind}: {d.detail}" for d in drift],
                "blocked": True,
            }
        transformed = []
        unmapped: list[str] = []
        for row in rows:
            canonical, missed = transform_row(adapter.profile.name, row.payload)
            canonical["record_id"] = row.record_id
            transformed.append((row, canonical))
            unmapped.extend(missed)
        report = check_rows(
            [c for _, c in transformed],
            required=["position_id", "client_id", "instrument", "notional"],
            numeric_ranges={"notional": (-10_000_000, 10_000_000)},
            key_field="position_id",
            reference_ids=reference_ids,
        )
        quarantined_by_index = {q.row_index: q for q in report.quarantined}
        loaded = 0
        with sqlite3.connect(self.db_path) as conn:
            for index, (row, canonical) in enumerate(transformed):
                if index in quarantined_by_index:
                    conn.execute(
                        "INSERT INTO quarantine VALUES (?, ?, ?)",
                        (row.record_id, quarantined_by_index[index].reason, adapter.profile.name),
                    )
                    continue
                cur = conn.execute(
                    """INSERT OR IGNORE INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (canonical["position_id"], canonical["client_id"], canonical["instrument"],
                     canonical["notional"], canonical["currency"], canonical["valuation_date"],
                     adapter.profile.name, row.schema_version),
                )
                if cur.rowcount:
                    loaded += 1
                    entry = LineageEntry(row.record_id, adapter.profile.name,
                                         row.schema_version, "transform_row v1", "contract v1")
                    self.lineage.record(entry)
                    conn.execute("INSERT INTO lineage VALUES (?, ?, ?, ?, ?)",
                                 (entry.record_id, entry.source, entry.schema_version,
                                  entry.transform, entry.contract_version))
                    self.index.add(
                        f"pos-{canonical['position_id']}",
                        f"{canonical['instrument']} position {canonical['position_id']} "
                        f"client {canonical['client_id']} notional {canonical['notional']} "
                        f"{canonical['currency']} valued {canonical['valuation_date']}",
                        sensitivity="internal",
                    )
        return {
            "loaded": loaded,
            "quarantined": report.quarantined_count,
            "quarantine_reasons": [f"{q.record_id}: {q.reason}" for q in report.quarantined],
            "violations": [],
            "drift": [f"{d.kind}: {d.detail}" for d in drift],
            "unmapped_columns": sorted(set(unmapped)),
            "blocked": False,
        }

    def feature_store_snapshot(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT position_id, client_id, instrument, notional, currency, valuation_date "
                "FROM positions ORDER BY position_id"
            ).fetchall()
        return [
            feature_snapshot(dict(zip(
                ["position_id", "client_id", "instrument", "notional", "currency", "valuation_date"], r)))
            for r in rows
        ]
