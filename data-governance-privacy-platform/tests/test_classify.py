"""Tests for the PII / sensitivity classifier."""

from governance.classify import classify_column


def test_email_by_name_and_value():
    c = classify_column("email", ["a@example.com", "b@example.org"])
    assert c.sensitivity == "confidential"
    assert c.rule == "name:email"


def test_email_by_value_only():
    c = classify_column("contact", ["a@example.com", "b@example.org"])
    assert c.sensitivity == "confidential"
    assert c.rule == "value:email"


def test_phone():
    c = classify_column("phone", ["+1-415-555-0132"])
    assert c.sensitivity == "confidential"
    assert c.rule == "name:phone"


def test_ssn():
    c = classify_column("ssn", ["123-45-6789"])
    assert c.sensitivity == "restricted"
    assert c.rule == "name:ssn"


def test_ssn_by_value_only():
    c = classify_column("tax_id", ["123-45-6789", "987-65-4321"])
    assert c.sensitivity == "restricted"
    assert c.rule == "value:ssn"


def test_person_name():
    c = classify_column("full_name", ["Alex Rivera"])
    assert c.sensitivity == "confidential"
    assert c.rule == "name:person-name"


def test_street_address():
    c = classify_column("street_address", ["482 Maple Ave, Buffalo, NY 14201"])
    assert c.sensitivity == "confidential"
    assert c.rule == "name:address"


def test_account_number():
    c = classify_column("account_number", ["1000000001234567"])
    assert c.sensitivity == "restricted"
    assert c.rule == "name:account-number"


def test_date_of_birth():
    c = classify_column("date_of_birth", ["1990-04-12"])
    assert c.sensitivity == "confidential"
    assert c.rule == "name:dob"


def test_dob_by_name_born():
    c = classify_column("born_on", ["1990-04-12", "1988-11-03"])
    assert c.sensitivity == "confidential"
    assert c.rule == "name:dob"


def test_plain_date_column_is_not_a_dob():
    # A YYYY-MM-DD value alone must not mark a column as a date of birth:
    # transaction dates share the same shape.
    c = classify_column("transaction_date", ["2026-10-02", "2026-10-05"])
    assert c.sensitivity == "internal"
    assert c.rule == "default:internal"


def test_plain_column_defaults_to_internal():
    c = classify_column("merchant", ["Corner Grocers", "City Transit"])
    assert c.sensitivity == "internal"
    assert c.rule == "default:internal"


def test_empty_samples_default_to_internal():
    c = classify_column("notes", [])
    assert c.sensitivity == "internal"
