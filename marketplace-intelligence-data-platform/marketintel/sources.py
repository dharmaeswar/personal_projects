"""Source adapters for heterogeneous external and internal feeds.

Every adapter yields RawRecord rows tagged with its source name and
schema version, so downstream stages always know where a row came from
and which shape it arrived in. The JSON API adapter models the real
produce/poll/commit pattern: paginated delivery with an injected
transient failure and a retry, so a flaky vendor feed does not kill a
run. Spark equivalent: one DataFrameReader per source, unioned after
mapping; the API adapter is the local stand-in for a REST/HTTP source.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RawRecord:
    source: str
    schema_version: str
    payload: dict
    ingested_at: str = ""


@dataclass
class FetchResult:
    records: list
    pages_fetched: int = 0
    retries: int = 0


class CsvFeedSource:
    """Reads a CSV feed file. `schema_version` is declared by the caller
    (the feed's own version header in production)."""

    def __init__(self, name, path, schema_version):
        self.name = name
        self.path = Path(path)
        self.schema_version = schema_version

    def fetch(self, ingested_at=""):
        records = []
        with self.path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                records.append(
                    RawRecord(
                        source=self.name,
                        schema_version=self.schema_version,
                        payload=dict(row),
                        ingested_at=ingested_at,
                    )
                )
        return FetchResult(records=records, pages_fetched=1)


class JsonApiSource:
    """Simulated paginated JSON API source.

    `pages` is a list of page dicts (each with a "records" list).
    `fail_on_page` names a 0-based page index whose FIRST fetch raises a
    transient error, modelling a flaky vendor API; the fetch retries
    once and succeeds, and `retries` records that it happened.
    """

    def __init__(self, name, pages, schema_version, fail_on_page=None):
        self.name = name
        self.pages = pages
        self.schema_version = schema_version
        self.fail_on_page = fail_on_page

    def fetch(self, ingested_at=""):
        records = []
        retries = 0
        for idx, page in enumerate(self.pages):
            attempts = 0
            while True:
                attempts += 1
                try:
                    if (
                        self.fail_on_page is not None
                        and idx == self.fail_on_page
                        and attempts == 1
                    ):
                        raise ConnectionError(
                            f"transient failure fetching page {idx} "
                            f"from {self.name}"
                        )
                    break
                except ConnectionError:
                    if attempts >= 2:
                        raise
                    retries += 1
            for row in page.get("records", []):
                records.append(
                    RawRecord(
                        source=self.name,
                        schema_version=self.schema_version,
                        payload=dict(row),
                        ingested_at=ingested_at,
                    )
                )
        return FetchResult(
            records=records, pages_fetched=len(self.pages), retries=retries
        )


class InternalAggregateSource:
    """Internal aggregates arrive as in-memory dicts (in production: a
    query against the internal warehouse). Same RawRecord shape, so the
    mapper and contract stages treat internal and external rows alike."""

    def __init__(self, name, rows, schema_version):
        self.name = name
        self.rows = rows
        self.schema_version = schema_version

    def fetch(self, ingested_at=""):
        return FetchResult(
            records=[
                RawRecord(
                    source=self.name,
                    schema_version=self.schema_version,
                    payload=dict(row),
                    ingested_at=ingested_at,
                )
                for row in self.rows
            ],
            pages_fetched=1,
        )


def load_json_pages(path):
    """Load a JSON file holding {"pages": [{"records": [...]}, ...]}."""
    with Path(path).open() as fh:
        return json.load(fh)["pages"]
