"""Tests for the deterministic triage agent."""

from detection.classifier import AttackScorer
from detection.triage import triage_message
from tests.test_features import LEGIT, PHISH

SCORER = AttackScorer()


def _triage(msg):
    return triage_message(msg, SCORER.score_message(msg))


def test_blocklisted_sender_is_quarantined():
    result = _triage({**PHISH, "sender": "billing@acmec0rp.com"})
    assert result["verdict"] == "quarantine"
    assert result["action"] == "quarantine_and_block_sender"
    assert result["confidence"] >= 0.95


def test_blocklisted_domain_is_quarantined():
    result = _triage({**PHISH, "sender": "x@acme-secure-login.xyz"})
    assert result["verdict"] == "quarantine"


def test_high_risk_phish_is_quarantined():
    result = _triage(PHISH)
    assert result["verdict"] == "quarantine"
    assert result["action"] == "quarantine"


def test_legit_internal_message_is_allowed():
    result = _triage(LEGIT)
    assert result["verdict"] == "allow"
    assert result["action"] == "deliver"


def test_medium_risk_message_is_escalated():
    # Borderline: external sender, one auth failure, mild urgency.
    msg = {
        **LEGIT,
        "sender": "carol.wu@external-vendor.com",
        "display_name": "Carol Wu",
        "reply_to": "carol.wu@external-vendor.com",
        "known_sender": False,
        "dmarc_pass": False,
        "subject": "Invoice attached — please review",
        "body": "Please review the attached invoice when you have a moment.",
        "attachments": ["invoice.pdf"],
    }
    result = _triage(msg)
    assert result["verdict"] == "escalate"
    assert result["action"] == "escalate_to_soc_analyst"


def test_allowlisted_domain_overrides_borderline_score():
    msg = {
        **LEGIT,
        "sender": "alice.johnson@acmecorp.com",
        "known_sender": False,
        "dmarc_pass": False,
        "subject": "Invoice attached",
        "body": "See the attached invoice.",
    }
    result = _triage(msg)
    assert result["verdict"] == "allow"


def test_triage_is_deterministic():
    assert _triage(PHISH) == _triage(PHISH)


def test_triage_steps_record_the_workflow():
    result = _triage(PHISH)
    step_names = [s["step"] for s in result["steps"]]
    assert step_names[0] == "gather_signals"
    assert "check_blocklist" in step_names
    assert "apply_policy" in step_names


def test_triage_rationale_mentions_score():
    result = _triage(PHISH)
    assert "risk score" in result["rationale"]
