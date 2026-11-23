"""Tests for security-master validations."""

from investment_data_validation.data import AS_OF, build_security_master
from investment_data_validation.security_master import (
    cusip_check_digit,
    isin_check_digit,
    valid_cusip,
    valid_isin,
    validate_security_master,
)


def _findings(report, check, record_id):
    return [f for f in report.findings
            if f.check == check and f.record_id == record_id]


def test_cusip_check_digit_roundtrip():
    body = "12345678"
    digit = cusip_check_digit(body)
    assert valid_cusip(body + str(digit))
    assert not valid_cusip(body + str((digit + 1) % 10))


def test_isin_check_digit_roundtrip():
    body = "US037833100"
    digit = isin_check_digit(body)
    assert valid_isin(body + str(digit))
    assert not valid_isin(body + str((digit + 1) % 10))


def test_bad_cusip_check_digit_flagged():
    report = validate_security_master(build_security_master(), AS_OF)
    assert _findings(report, "valid_cusip", "SEC-9001")


def test_duplicate_cusip_flagged():
    report = validate_security_master(build_security_master(), AS_OF)
    assert _findings(report, "unique_cusip", "SEC-9002")


def test_maturity_before_issue_flagged():
    report = validate_security_master(build_security_master(), AS_OF)
    assert _findings(report, "maturity_after_issue", "SEC-9003")


def test_negative_coupon_and_zero_face_flagged():
    report = validate_security_master(build_security_master(), AS_OF)
    assert _findings(report, "coupon_range", "SEC-9004")
    assert _findings(report, "face_value", "SEC-9004")


def test_clean_securities_pass():
    rows = build_security_master()[:36]
    report = validate_security_master(rows, AS_OF)
    assert report.failed == 0
    assert report.records_checked == 36


def test_missing_field_flagged():
    row = dict(build_security_master()[0])
    row["ticker"] = ""
    report = validate_security_master([row], AS_OF)
    assert _findings(report, "required_fields", row["security_id"])


def test_status_mismatch_is_warning_not_failure():
    row = dict(build_security_master()[0])
    row["status"] = "Active"
    row["maturity_date"] = "2020-01-01"
    row["issue_date"] = "2015-01-01"
    report = validate_security_master([row], AS_OF)
    assert report.failed == 0
    assert _findings(report, "status_consistent", row["security_id"])
    assert report.warnings == 1
