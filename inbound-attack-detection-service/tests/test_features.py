"""Tests for feature extraction."""

from detection.features import (
    extract_features,
    extract_urls,
    feature_vector,
    is_lookalike_domain,
)

LEGIT = {
    "sender": "alice.johnson@acmecorp.com",
    "display_name": "Alice Johnson",
    "reply_to": "alice.johnson@acmecorp.com",
    "subject": "Q3 roadmap review",
    "body": "Hi team, sharing the notes from today's review.",
    "attachments": ["notes.pdf"],
    "spf_pass": True, "dkim_pass": True, "dmarc_pass": True,
    "known_sender": True,
}

PHISH = {
    "sender": "sarah chen@acmecorp-support.xyz",
    "display_name": "Sarah Chen",
    "reply_to": "support@acmec0rp.com",
    "subject": "URGENT: Verify your account immediately",
    "body": "Verify your account immediately at https://acme-secure-login.xyz/verify. "
            "Your password expires today.",
    "attachments": ["invoice.zip"],
    "spf_pass": False, "dkim_pass": False, "dmarc_pass": False,
    "known_sender": False,
}


def test_legit_message_has_no_attack_features():
    f = extract_features(LEGIT)
    assert f["sender_domain_mismatch"] is False
    assert f["display_name_spoof"] is False
    assert f["reply_to_mismatch"] is False
    assert f["auth_failures"] == 0
    assert f["risky_attachment_count"] == 0
    assert f["urgency_keyword_count"] == 0


def test_phish_message_flags_identity_and_auth():
    f = extract_features(PHISH)
    assert f["sender_domain_mismatch"] is True
    assert f["display_name_spoof"] is True  # exec name, wrong domain
    assert f["reply_to_mismatch"] is True
    assert f["auth_failures"] == 3
    assert f["suspicious_tld_count"] == 1
    assert f["risky_attachment_count"] == 1
    assert f["urgency_keyword_count"] >= 2


def test_extract_urls_finds_links_in_body():
    urls = extract_urls("see https://example.com/a and http://192.168.0.1/x now")
    assert urls == ["https://example.com/a", "http://192.168.0.1/x"]


def test_ip_host_url_detected():
    f = extract_features({**LEGIT, "body": "reset here http://10.0.0.5/reset"})
    assert f["ip_host_url_count"] == 1


def test_lookalike_domain_near_miss():
    assert is_lookalike_domain("acmec0rp.com", "acmecorp.com") is True
    assert is_lookalike_domain("acmecorp.com", "acmecorp.com") is False
    assert is_lookalike_domain("totallydifferent.com", "acmecorp.com") is False


def test_free_sender_domain_flag():
    f = extract_features({**LEGIT, "sender": "someone@gmail.com"})
    assert f["free_sender_domain"] is True


def test_subject_all_caps_flag():
    f = extract_features({**LEGIT, "subject": "URGENT ACTION REQUIRED"})
    assert f["subject_all_caps"] is True
    f2 = extract_features({**LEGIT, "subject": "Normal subject line"})
    assert f2["subject_all_caps"] is False


def test_feature_vector_is_numeric():
    v = feature_vector(extract_features(PHISH))
    assert all(isinstance(x, float) for x in v.values())
    assert v["auth_failures"] == 3.0
    assert v["display_name_spoof"] == 1.0
