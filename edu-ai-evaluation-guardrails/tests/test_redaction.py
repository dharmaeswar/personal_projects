"""Tests for PII redaction."""

from edu_ai_evaluation_guardrails.redaction import contains_pii, redact_text


def test_redacts_email_and_student_id():
    text = "Contact maya.chen@example.edu, SID-482913, about the course."
    redacted, counts = redact_text(text)
    assert "maya.chen@example.edu" not in redacted
    assert "482913" not in redacted
    assert "[EMAIL]" in redacted
    assert "[STUDENT-ID]" in redacted
    assert counts["[EMAIL]"] == 1
    assert counts["[STUDENT-ID]"] == 1
    assert not contains_pii(redacted)


def test_redacts_known_names():
    text = "Maya Chen asked about fractions today."
    redacted, counts = redact_text(text, known_names=("Maya Chen",))
    assert "Maya Chen" not in redacted
    assert "[NAME]" in redacted
    assert counts["[NAME]"] == 1


def test_redacts_phone():
    text = "Call me at (716) 555-0142 after class."
    redacted, counts = redact_text(text)
    assert "716" not in redacted
    assert "[PHONE]" in redacted
    assert counts["[PHONE]"] == 1


def test_clean_text_unchanged():
    text = "What is 2 + 2?"
    redacted, counts = redact_text(text)
    assert redacted == text
    assert counts == {}


def test_contains_pii_detects_leftover_email():
    assert contains_pii("reach me at a@b.edu")
    assert not contains_pii("reach me at [EMAIL]")
