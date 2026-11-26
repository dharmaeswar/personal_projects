"""Ingest for the home-health warehouse.

Two sources, one record shape:

- CSV visit feed (field devices): one row per home-health visit.
- Paginated JSON referral API (the integration layer, MuleSoft-style):
  referrals/orders that visits must match. The client retries transient
  failures once, the way a real integration flow would.

Every record is tagged with ``source`` and ``schema_version``. Malformed
rows are collected in ``errors`` and reported, never silently dropped.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

VISIT_FIELDS = (
    "visit_id",
    "patient_key",
    "clinician_id",
    "visit_date",
    "duration_min",
    "care_plan",
    "assessment_score",
)

REFERRAL_FIELDS = (
    "referral_id",
    "patient_key",
    "clinician_id",
    "ordered_date",
    "service_type",
    "status",
)


@dataclass
class IngestResult:
    records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    api_retries: int = 0


def read_visit_csv(path: str | Path) -> IngestResult:
    """Parse the CSV visit feed. Returns records + a list of parse errors."""
    result = IngestResult()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for lineno, row in enumerate(reader, start=2):
            missing = [f for f in VISIT_FIELDS if f not in row]
            if missing:
                result.errors.append(
                    f"line {lineno}: missing columns {missing}"
                )
                continue
            record = {f: (row[f] or "").strip() for f in VISIT_FIELDS}
            record["source"] = "visit_feed_csv"
            record["schema_version"] = "v1"
            try:
                record["duration_min"] = int(record["duration_min"])
            except ValueError:
                result.errors.append(
                    f"line {lineno}: duration_min "
                    f"'{record['duration_min']}' is not an integer"
                )
                continue
            try:
                record["assessment_score"] = int(record["assessment_score"])
            except ValueError:
                result.errors.append(
                    f"line {lineno}: assessment_score "
                    f"'{record['assessment_score']}' is not an integer"
                )
                continue
            result.records.append(record)
    return result


class TransientApiError(Exception):
    """A transient failure from the referral API (retryable)."""


class ReferralApiClient:
    """Simulated paginated referral API.

    ``pages`` is a list of pages (each a list of referral dicts).
    ``fail_first_fetch`` injects one transient failure on the first page
    fetch so the retry path is exercised; a real client would see this as
    a 502/503 from the integration layer.
    """

    def __init__(self, pages: list[list[dict]], fail_first_fetch: bool = False):
        self._pages = pages
        self._fail_first_fetch = fail_first_fetch
        self._fetch_count = 0

    def fetch_page(self, page: int) -> list[dict]:
        self._fetch_count += 1
        if self._fail_first_fetch and self._fetch_count == 1:
            raise TransientApiError("503 Service Unavailable (simulated)")
        if page < 0 or page >= len(self._pages):
            return []
        return self._pages[page]

    @property
    def page_count(self) -> int:
        return len(self._pages)


def fetch_referrals(client: ReferralApiClient, max_retries: int = 1) -> IngestResult:
    """Fetch every page of referrals, retrying transient failures."""
    result = IngestResult()
    for page in range(client.page_count):
        attempts = 0
        while True:
            try:
                rows = client.fetch_page(page)
                break
            except TransientApiError:
                attempts += 1
                result.api_retries += 1
                if attempts > max_retries:
                    result.errors.append(
                        f"page {page}: referral API failed after "
                        f"{max_retries} retries"
                    )
                    rows = []
                    break
        for row in rows:
            missing = [f for f in REFERRAL_FIELDS if f not in row]
            if missing:
                result.errors.append(
                    f"page {page}: referral missing columns {missing}"
                )
                continue
            record = {f: str(row[f]).strip() for f in REFERRAL_FIELDS}
            record["source"] = "referral_api"
            record["schema_version"] = "v2"
            result.records.append(record)
    return result


def load_referral_fixture(path: str | Path) -> list[list[dict]]:
    """Load the seeded referral fixture (a list of pages)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["pages"]
