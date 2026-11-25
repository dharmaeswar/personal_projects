import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics_solutions.governance import AccessPolicy, classify_column, mask_value


def test_classify_by_column_name_and_by_value():
    assert classify_column("holder_email") == "email"
    assert classify_column("ssn") == "ssn"
    assert classify_column("phone_number") == "phone"
    assert classify_column("date_of_birth") == "dob"
    assert classify_column("premium_annual") == "none"
    assert classify_column("contact", ["a@example.com"]) == "email"
    assert classify_column("contact", ["123-45-6789"]) == "ssn"
    assert classify_column("contact", ["plain text"]) == "none"


def test_mask_methods():
    assert mask_value("a@example.com", "email") == "[REDACTED]"
    assert mask_value("414-555-0123", "phone", "last4") == "***-0123"
    hashed = mask_value("123-45-6789", "ssn", "hash")
    assert len(hashed) == 16 and hashed != "123-45-6789"
    assert mask_value("keep me", "none") == "keep me"
    with pytest.raises(ValueError):
        mask_value("x", "email", "shout")


def test_analyst_never_sees_restricted_columns_engineer_sees_masked():
    classes = {"holder_id": "none", "email": "email", "premium_annual": "none"}
    policy = AccessPolicy(classes)
    row = {"holder_id": "H1", "email": "a@example.com", "premium_annual": 1000}
    analyst = policy.project_row(row, "analyst")
    assert "email" not in analyst
    assert analyst["holder_id"] == "H1"
    engineer = policy.project_row(row, "engineer")
    assert engineer["email"] == "[REDACTED]"
    assert engineer["premium_annual"] == 1000


def test_auditor_access_is_logged():
    classes = {"email": "email"}
    policy = AccessPolicy(classes)
    policy.project_row({"email": "a@example.com"}, "auditor")
    assert len(policy.access_log) == 1
    assert policy.access_log[0]["role"] == "auditor"
