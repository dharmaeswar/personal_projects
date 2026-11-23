from clinical_agent.phi import contains_phi, redact


def test_redacts_medical_record_number():
    redacted, findings = redact("Patient MRN-482913 needs a follow-up.")
    assert "MRN-482913" not in redacted
    assert "MRN" in findings


def test_redacts_date_of_birth():
    redacted, findings = redact("Born 03/14/1962, diabetic since 2019.")
    assert "03/14/1962" not in redacted
    assert "DOB" in findings


def test_redacts_phone_number():
    redacted, findings = redact("Call the patient at 716-555-0142.")
    assert "716-555-0142" not in redacted
    assert "PHONE" in findings


def test_redacts_patient_name():
    redacted, findings = redact("Alice Johnson missed her visit.")
    assert "Alice Johnson" not in redacted
    assert "NAME" in findings


def test_redacts_email():
    redacted, findings = redact("Email robert.chen@example.org the summary.")
    assert "robert.chen@example.org" not in redacted
    assert "EMAIL" in findings


def test_contains_phi_flags_phi_text():
    assert contains_phi("MRN-917204, call 716-555-0187")


def test_contains_phi_clear_for_clean_text():
    assert not contains_phi("Check HbA1c every 3 to 6 months.")


def test_clean_text_is_unchanged():
    redacted, findings = redact("Review blood pressure at every visit.")
    assert redacted == "Review blood pressure at every visit."
    assert findings == []
