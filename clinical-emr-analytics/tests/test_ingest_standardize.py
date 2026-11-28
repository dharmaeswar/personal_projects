"""Tests for ingest and standardization."""

import os

from emr_analytics.ingest import load_csv, load_feeds
from emr_analytics.standardize import (
    standardize_lab,
    standardize_medication,
    standardize_vital,
)

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data")


def test_load_feeds_counts():
    feeds, malformed = load_feeds(DATA)
    assert len(feeds["encounters"]) == 12
    assert len(feeds["vitals"]) == 42
    assert len(feeds["labs"]) == 26
    assert len(feeds["medications"]) == 16
    assert malformed == {}


def test_load_csv_malformed_row_reported(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("a,b\n1,2\n3\n", encoding="utf-8")
    rows, malformed = load_csv(str(path))
    assert len(rows) == 1
    assert len(malformed) == 1
    assert malformed[0]["line"] == 3


def test_temp_f_converted_to_c():
    row, notes = standardize_vital(
        {"vital_type": "TEMP_F", "value": "98.6", "unit": "F"})
    assert row["vital_type"] == "TEMP_C"
    assert row["unit"] == "C"
    assert abs(float(row["value"]) - 37.0) < 0.01
    assert notes


def test_non_temp_vital_unchanged():
    row, notes = standardize_vital(
        {"vital_type": "HEART_RATE", "value": "72", "unit": "bpm"})
    assert row["vital_type"] == "HEART_RATE"
    assert row["value"] == "72"
    assert notes == []


def test_lab_aliases_mapped():
    row, _ = standardize_lab({"test_name": "HGB"})
    assert row["test_name"] == "Hemoglobin"
    row, _ = standardize_lab({"test_name": "A1C"})
    assert row["test_name"] == "HbA1c"
    row, _ = standardize_lab({"test_name": "LDL Cholesterol"})
    assert row["test_name"] == "LDL Cholesterol"


def test_unknown_lab_name_kept_with_note():
    row, notes = standardize_lab({"test_name": "Mystery Panel"})
    assert row["test_name"] == "Mystery Panel"
    assert notes


def test_mcg_dose_converted_to_mg():
    row, _ = standardize_medication({"dose": "75", "dose_unit": "mcg"})
    assert abs(float(row["dose_mg"]) - 0.075) < 0.0001


def test_mg_dose_unchanged():
    row, _ = standardize_medication({"dose": "500", "dose_unit": "mg"})
    assert abs(float(row["dose_mg"]) - 500.0) < 0.0001


def test_units_dose_has_no_mg():
    row, _ = standardize_medication({"dose": "10", "dose_unit": "units"})
    assert row["dose_mg"] == ""


def test_unknown_dose_unit_noted():
    _, notes = standardize_medication({"dose": "20", "dose_unit": "xyz"})
    assert notes
