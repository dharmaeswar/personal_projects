"""Tests for the six data-quality rules."""

from datetime import date

from homehealth import quality

TODAY = date(2026, 11, 26)


def good_visit(**overrides):
    record = {
        "visit_id": "V001",
        "patient_key": "P001",
        "clinician_id": "C101",
        "visit_date": "2026-11-20",
        "duration_min": 45,
        "care_plan": "wound-care",
        "assessment_score": 82,
    }
    record.update(overrides)
    return record


def test_valid_visit_passes_all_rules():
    valid, quarantined = quality.validate_visits([good_visit()], TODAY)
    assert len(valid) == 1
    assert quarantined == []


def test_future_visit_date_quarantined():
    _, quarantined = quality.validate_visits(
        [good_visit(visit_date="2027-06-01")], TODAY
    )
    assert len(quarantined) == 1
    assert any("future" in r for r in quarantined[0]["_quarantine_reasons"])


def test_bad_visit_date_format_quarantined():
    _, quarantined = quality.validate_visits(
        [good_visit(visit_date="20/11/2026")], TODAY
    )
    assert len(quarantined) == 1
    assert any("visit_date" in r for r in quarantined[0]["_quarantine_reasons"])


def test_negative_duration_quarantined():
    _, quarantined = quality.validate_visits(
        [good_visit(duration_min=-30)], TODAY
    )
    assert len(quarantined) == 1
    assert any("duration_min" in r for r in quarantined[0]["_quarantine_reasons"])


def test_duration_bounds_enforced():
    _, quarantined = quality.validate_visits(
        [good_visit(duration_min=4), good_visit(visit_id="V002", duration_min=481)],
        TODAY,
    )
    assert len(quarantined) == 2


def test_missing_clinician_quarantined():
    _, quarantined = quality.validate_visits(
        [good_visit(clinician_id="")], TODAY
    )
    assert len(quarantined) == 1
    assert any("clinician_id" in r for r in quarantined[0]["_quarantine_reasons"])


def test_missing_patient_key_quarantined():
    _, quarantined = quality.validate_visits(
        [good_visit(patient_key="  ")], TODAY
    )
    assert len(quarantined) == 1
    assert any("patient_key" in r for r in quarantined[0]["_quarantine_reasons"])


def test_assessment_score_out_of_range_quarantined():
    _, quarantined = quality.validate_visits(
        [good_visit(assessment_score=101)], TODAY
    )
    assert len(quarantined) == 1
    assert any("assessment_score" in r for r in quarantined[0]["_quarantine_reasons"])


def test_duplicate_visit_id_keeps_first_only():
    valid, quarantined = quality.validate_visits(
        [good_visit(), good_visit(visit_date="2026-11-21")], TODAY
    )
    assert len(valid) == 1
    assert len(quarantined) == 1
    assert any("duplicate" in r for r in quarantined[0]["_quarantine_reasons"])


def test_multiple_failures_all_reported():
    _, quarantined = quality.validate_visits(
        [good_visit(clinician_id="", duration_min=-5)], TODAY
    )
    assert len(quarantined[0]["_quarantine_reasons"]) == 2
