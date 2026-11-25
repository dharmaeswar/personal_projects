"""Source adapters for client and legacy data environments.

One interface, three shapes of legacy reality a forward-deployed pod meets:
a Postgres table dump (CSV), an Oracle-style pipe-delimited extract, and a
paginated REST API with transient failures. Every row is tagged with its
source system and schema version so drift and lineage stay traceable.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field


@dataclass
class SourceRow:
    """One raw record as read from a client source, before transformation."""

    source: str
    schema_version: str
    record_id: str
    payload: dict
    raw_line: str = ""


@dataclass
class SourceProfile:
    """Where a source lives and how the pod reaches it."""

    name: str
    system: str  # e.g. "Postgres", "Oracle", "REST API"
    location: str  # "on-prem", "cloud", "hybrid"
    owner_team: str


class SourceAdapter:
    """Common adapter interface: read rows, capture the schema seen."""

    def __init__(self, profile: SourceProfile):
        self.profile = profile
        self.schema_seen: list[str] = []

    def read(self) -> list[SourceRow]:
        raise NotImplementedError


class PostgresDumpAdapter(SourceAdapter):
    """Reads a Postgres table dump delivered as CSV (v1 or v2 schema)."""

    def __init__(self, profile: SourceProfile, csv_text: str, schema_version: str):
        super().__init__(profile)
        self.csv_text = csv_text
        self.schema_version = schema_version

    def read(self) -> list[SourceRow]:
        reader = csv.DictReader(io.StringIO(self.csv_text))
        self.schema_seen = list(reader.fieldnames or [])
        rows = []
        for line_no, row in enumerate(reader, start=2):
            record_id = row.get("position_id") or row.get("pos_id") or f"line-{line_no}"
            rows.append(
                SourceRow(
                    source=self.profile.name,
                    schema_version=self.schema_version,
                    record_id=str(record_id),
                    payload={k: (v if v != "" else None) for k, v in row.items()},
                    raw_line=json.dumps(row, sort_keys=True),
                )
            )
        return rows


class OracleExtractAdapter(SourceAdapter):
    """Reads an Oracle-style pipe-delimited extract with a header row."""

    def __init__(self, profile: SourceProfile, text: str, schema_version: str):
        super().__init__(profile)
        self.text = text
        self.schema_version = schema_version

    def read(self) -> list[SourceRow]:
        lines = [ln for ln in self.text.strip().splitlines() if ln.strip()]
        header = [h.strip() for h in lines[0].split("|")]
        self.schema_seen = header
        rows = []
        for line in lines[1:]:
            values = [v.strip() for v in line.split("|")]
            payload = dict(zip(header, values))
            record_id = payload.get("RISK_ID") or payload.get("risk_id") or "unknown"
            rows.append(
                SourceRow(
                    source=self.profile.name,
                    schema_version=self.schema_version,
                    record_id=str(record_id),
                    payload={k: (v if v != "" else None) for k, v in payload.items()},
                    raw_line=line,
                )
            )
        return rows


class RestApiAdapter(SourceAdapter):
    """Reads a paginated REST API; retries once on an injected transient failure."""

    def __init__(self, profile: SourceProfile, pages: list[list[dict]], fail_page: int = -1):
        super().__init__(profile)
        self.pages = pages
        self.fail_page = fail_page
        self.retries_used = 0

    def _fetch_page(self, index: int) -> list[dict]:
        if index == self.fail_page and self.retries_used == 0:
            self.retries_used += 1
            raise ConnectionError(f"transient failure on page {index}")
        return self.pages[index]

    def read(self) -> list[SourceRow]:
        rows: list[SourceRow] = []
        for index in range(len(self.pages)):
            try:
                page = self._fetch_page(index)
            except ConnectionError:
                page = self._fetch_page(index)  # one retry, then it must succeed
            for item in page:
                if not self.schema_seen:
                    self.schema_seen = sorted(item.keys())
                record_id = str(item.get("client_id") or item.get("id") or "unknown")
                rows.append(
                    SourceRow(
                        source=self.profile.name,
                        schema_version="v1",
                        record_id=record_id,
                        payload=dict(item),
                        raw_line=json.dumps(item, sort_keys=True),
                    )
                )
        return rows
