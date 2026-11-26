"""Tests for ingest: CSV visit feed + paginated referral API."""

from pathlib import Path

import pytest

from homehealth import ingest

BASE = Path(__file__).resolve().parent.parent


def test_read_visit_csv_parses_all_rows():
    result = ingest.read_visit_csv(BASE / "data" / "visits.csv")
    assert len(result.records) == 16
    assert result.errors == []
    assert result.records[0]["visit_id"] == "V001"
    assert result.records[0]["duration_min"] == 45
    assert result.records[0]["source"] == "visit_feed_csv"
    assert result.records[0]["schema_version"] == "v1"


def test_read_visit_csv_rejects_bad_integer(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "visit_id,patient_key,clinician_id,visit_date,duration_min,"
        "care_plan,assessment_score\n"
        "V100,P001,C101,2026-11-10,forty,wound-care,80\n",
        encoding="utf-8",
    )
    result = ingest.read_visit_csv(bad)
    assert result.records == []
    assert len(result.errors) == 1
    assert "duration_min" in result.errors[0]


def test_fetch_referrals_paginates_all_pages():
    pages = ingest.load_referral_fixture(BASE / "data" / "referrals.json")
    client = ingest.ReferralApiClient(pages)
    result = ingest.fetch_referrals(client)
    assert len(result.records) == 6
    assert result.errors == []
    assert result.api_retries == 0
    assert {r["referral_id"] for r in result.records} == {
        "R1001", "R1002", "R1003", "R1004", "R1005", "R1006",
    }
    assert result.records[0]["schema_version"] == "v2"


def test_fetch_referrals_retries_transient_failure():
    pages = ingest.load_referral_fixture(BASE / "data" / "referrals.json")
    client = ingest.ReferralApiClient(pages, fail_first_fetch=True)
    result = ingest.fetch_referrals(client)
    assert len(result.records) == 6
    assert result.api_retries == 1
    assert result.errors == []


def test_fetch_referrals_gives_up_after_retries():
    pages = ingest.load_referral_fixture(BASE / "data" / "referrals.json")

    class AlwaysFailing(ingest.ReferralApiClient):
        def fetch_page(self, page):
            raise ingest.TransientApiError("503")

    result = ingest.fetch_referrals(AlwaysFailing(pages), max_retries=1)
    assert result.records == []
    assert len(result.errors) == 2  # one per page
    assert result.api_retries == 4  # 2 attempts per page
