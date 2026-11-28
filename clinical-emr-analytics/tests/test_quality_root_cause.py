"""Tests for data-quality rules and root-cause analysis."""

import os
from datetime import date

from emr_analytics.ingest import load_feeds
from emr_analytics.quality import check_lab, check_medication, check_vital, run_quality
from emr_analytics.root_cause import analyze
from emr_analytics.standardize import standardize_feeds

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data")
RUN_DATE = date(2026, 11, 28)
ENCOUNTERS = {"E001", "E002"}


def test_out_of_range_vital():
    rules = check_vital({"encounter_id": "E001", "vital_type": "HEART_RATE",
                         "value": "250", "recorded_at": "2026-10-01T09:00"},
                        ENCOUNTERS, set(), RUN_DATE)
    assert rules == ["OUT_OF_RANGE"]


def test_future_vital():
    rules = check_vital({"encounter_id": "E001", "vital_type": "HEART_RATE",
                         "value": "72", "recorded_at": "2027-01-15T09:00"},
                        ENCOUNTERS, set(), RUN_DATE)
    assert rules == ["FUTURE_TIMESTAMP"]


def test_unknown_encounter_vital():
    rules = check_vital({"encounter_id": "E999", "vital_type": "HEART_RATE",
                         "value": "72", "recorded_at": "2026-10-01T09:00"},
                        ENCOUNTERS, set(), RUN_DATE)
    assert rules == ["UNKNOWN_ENCOUNTER"]


def test_duplicate_vital_second_copy_flagged():
    seen = set()
    row = {"encounter_id": "E001", "vital_type": "HEART_RATE", "value": "72",
           "recorded_at": "2026-10-01T09:00"}
    assert check_vital(row, ENCOUNTERS, seen, RUN_DATE) == []
    assert check_vital(row, ENCOUNTERS, seen, RUN_DATE) == ["DUPLICATE"]


def test_lab_result_before_collection():
    rules = check_lab({"encounter_id": "E001", "test_name": "Creatinine",
                       "result_value": "1.1", "collected_at": "2026-10-01T10:00",
                       "result_at": "2026-10-01T09:00"},
                      ENCOUNTERS, set(), RUN_DATE)
    assert rules == ["RESULT_BEFORE_COLLECTION"]


def test_lab_negative_result_out_of_range():
    rules = check_lab({"encounter_id": "E001", "test_name": "Hemoglobin",
                       "result_value": "-3.0", "collected_at": "2026-10-01T10:00",
                       "result_at": "2026-10-01T12:00"},
                      ENCOUNTERS, set(), RUN_DATE)
    assert rules == ["OUT_OF_RANGE"]


def test_medication_zero_dose_and_bad_unit():
    rules = check_medication({"encounter_id": "E001", "dose": "0",
                              "dose_unit": "mg"}, ENCOUNTERS, set(), RUN_DATE)
    assert rules == ["INVALID_DOSE"]
    rules = check_medication({"encounter_id": "E001", "dose": "20",
                              "dose_unit": "xyz"}, ENCOUNTERS, set(), RUN_DATE)
    assert rules == ["INVALID_DOSE"]


def test_full_run_quarantine_counts():
    feeds, _ = load_feeds(DATA)
    standardized, _ = standardize_feeds(feeds)
    result = run_quality(standardized, RUN_DATE)
    assert len(result["quarantined"]) == 12
    by_feed = {}
    for item in result["quarantined"]:
        by_feed[item["feed"]] = by_feed.get(item["feed"], 0) + 1
    assert by_feed == {"vitals": 5, "labs": 4, "medications": 3}
    assert len(result["clean"]["vitals"]) == 37
    assert len(result["clean"]["labs"]) == 22
    assert len(result["clean"]["medications"]) == 13


def test_quarantined_rows_never_in_clean():
    feeds, _ = load_feeds(DATA)
    standardized, _ = standardize_feeds(feeds)
    result = run_quality(standardized, RUN_DATE)
    bad_ids = {q["row"].get("vital_id") or q["row"].get("lab_id")
               or q["row"].get("med_id")
               for q in result["quarantined"]}
    clean_ids = {r.get("vital_id") for r in result["clean"]["vitals"]}
    clean_ids |= {r.get("lab_id") for r in result["clean"]["labs"]}
    clean_ids |= {r.get("med_id") for r in result["clean"]["medications"]}
    assert not (bad_ids & clean_ids)


def test_root_cause_sorted_and_sums():
    feeds, _ = load_feeds(DATA)
    standardized, _ = standardize_feeds(feeds)
    result = run_quality(standardized, RUN_DATE)
    findings = analyze(result["quarantined"])
    assert findings[0]["count"] >= findings[-1]["count"]
    assert sum(f["count"] for f in findings) == 12
    top = findings[0]
    assert top["count"] == 2
    assert top["candidate_cause"] and top["suggested_fix"]
    assert all(f["share_pct"] > 0 for f in findings)
