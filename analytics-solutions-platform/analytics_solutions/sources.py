"""Multi-source ingest for the analytics solutions platform.

Sources are adapters over a common interface: each returns rows tagged with
``source``, ``schema_version`` and ``ingested_at``. The raw zone is a
partitioned lake layout (``lake/raw/<source>/date=YYYY-MM-DD/part.jsonl``),
the local stand-in for an S3 raw zone.
"""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass
class IngestedRow:
    """One row after ingest, with provenance attached."""

    data: dict
    source: str
    schema_version: str
    ingested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "data": self.data,
            "source": self.source,
            "schema_version": self.schema_version,
            "ingested_at": self.ingested_at,
        }


class CsvSource:
    """Ingest rows from a CSV string (e.g. a policy extract)."""

    def __init__(self, name: str, schema_version: str = "1.0"):
        self.name = name
        self.schema_version = schema_version

    def read(self, csv_text: str) -> list[IngestedRow]:
        rows: list[IngestedRow] = []
        reader = csv.DictReader(io.StringIO(csv_text))
        for raw in reader:
            rows.append(IngestedRow(data=dict(raw), source=self.name,
                                    schema_version=self.schema_version))
        return rows


class JsonLinesSource:
    """Ingest rows from JSON-lines text (e.g. an advisor activity feed)."""

    def __init__(self, name: str, schema_version: str = "1.0"):
        self.name = name
        self.schema_version = schema_version

    def read(self, jsonl_text: str) -> list[IngestedRow]:
        rows: list[IngestedRow] = []
        for line in jsonl_text.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(IngestedRow(data=json.loads(line), source=self.name,
                                    schema_version=self.schema_version))
        return rows


class PagedApiSource:
    """Ingest rows from a paginated API (simulated by a list of pages).

    Retries one transient failure per page, then raises. Mirrors the
    paginated-extract pattern used for third-party advisor systems.
    """

    def __init__(self, name: str, pages: list[list[dict]], schema_version: str = "1.0",
                 fail_page_once: int | None = None):
        self.name = name
        self.pages = pages
        self.schema_version = schema_version
        self.fail_page_once = fail_page_once
        self._failed: set[int] = set()

    def read(self) -> list[IngestedRow]:
        rows: list[IngestedRow] = []
        for idx, page in enumerate(self.pages):
            if self.fail_page_once == idx and idx not in self._failed:
                self._failed.add(idx)
                page = self._fetch_page(idx)  # retry once after a transient failure
            for item in page:
                rows.append(IngestedRow(data=dict(item), source=self.name,
                                        schema_version=self.schema_version))
        return rows

    def _fetch_page(self, idx: int) -> list[dict]:
        return self.pages[idx]


def raw_partition_path(lake_root: str, source: str, day: date) -> str:
    """Partitioned raw-zone path: lake/raw/<source>/date=YYYY-MM-DD/part.jsonl."""
    return os.path.join(lake_root, "raw", source, f"date={day.isoformat()}", "part.jsonl")


def write_raw_zone(rows: list[IngestedRow], lake_root: str, day: date) -> list[str]:
    """Write rows to their source/date partitions. Returns the files written."""
    by_source: dict[str, list[IngestedRow]] = {}
    for row in rows:
        by_source.setdefault(row.source, []).append(row)
    written: list[str] = []
    for source, source_rows in sorted(by_source.items()):
        path = raw_partition_path(lake_root, source, day)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for row in source_rows:
                fh.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")
        written.append(path)
    return written


def read_raw_zone(lake_root: str, source: str, day: date) -> list[IngestedRow]:
    """Read one raw partition back."""
    path = raw_partition_path(lake_root, source, day)
    rows: list[IngestedRow] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            rows.append(IngestedRow(data=obj["data"], source=obj["source"],
                                    schema_version=obj["schema_version"],
                                    ingested_at=obj["ingested_at"]))
    return rows
