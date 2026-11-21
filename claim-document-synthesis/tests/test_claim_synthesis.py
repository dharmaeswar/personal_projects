"""Tests for the claim-document-synthesis service."""
import json
import threading
import urllib.request
import urllib.error

import pytest

from claim_synthesis.api import make_handler
from claim_synthesis.documents import generate_documents
from claim_synthesis.extraction import (
    extract_facts, missing_facts, needs_review, overall_confidence)
from claim_synthesis.service import ClaimSynthesisService
from claim_synthesis.synthesis import synthesize_summary

from http.server import ThreadingHTTPServer


FULL_NARRATIVE = (
    "On 2026-09-14, Maria Garcia sustained a fracture to the ankle in a "
    "workplace incident. Treated at Riverside General Hospital. "
    "Total claimed amount $12,500."
)


def _doc(claim_id="CLM-1", tenant="tenant_acme", narrative=FULL_NARRATIVE):
    return {"claim_id": claim_id, "tenant_id": tenant,
            "claimant_name": "Maria Garcia",
            "submitted_date": "2026-11-10", "narrative": narrative}


# --- extraction ---

def test_extract_full_narrative():
    facts = extract_facts(FULL_NARRATIVE)
    assert facts["injury_type"]["value"] == "fracture"
    assert facts["body_part"]["value"] == "ankle"
    assert facts["incident_date"]["value"] == "2026-09-14"
    assert facts["treatment_provider"]["value"] == "Riverside General Hospital"
    assert facts["claimed_amount"]["value"] == 12500.0
    assert overall_confidence(facts) == 1.0
    assert not needs_review(facts)


def test_extract_missing_facts_go_to_review():
    facts = extract_facts("Maria Garcia sustained a sprain to the wrist.")
    assert facts["incident_date"]["value"] is None
    assert facts["claimed_amount"]["value"] is None
    assert missing_facts(facts) == ["incident_date", "treatment_provider",
                                    "claimed_amount"]
    assert needs_review(facts)


def test_extract_amount_with_cents_and_commas():
    facts = extract_facts("Amount claimed: $42,100.50.")
    assert facts["claimed_amount"]["value"] == 42100.50


def test_extract_unknown_provider_is_low_confidence():
    facts = extract_facts(
        "Treated at Springfield Clinic for a burn. Incident on 2026-08-02.")
    assert facts["treatment_provider"]["value"] == "Springfield Clinic"
    assert facts["treatment_provider"]["confidence"] == 0.6


# --- synthesis ---

def test_synthesize_summary_uses_facts_only():
    facts = extract_facts(FULL_NARRATIVE)
    summary = synthesize_summary("CLM-1", "Maria Garcia", facts)
    assert "fracture" in summary["headline"]
    assert "ankle" in summary["headline"]
    assert "2026-09-14" in summary["details"]
    assert "$12,500.00" in summary["details"]
    assert summary["flags"] == []
    assert summary["source"] == "template"


def test_synthesize_summary_flags_missing_facts():
    facts = extract_facts("Maria Garcia sustained a sprain to the wrist.")
    summary = synthesize_summary("CLM-9", "Maria Garcia", facts)
    assert "missing incident_date" in summary["flags"]
    assert "missing claimed_amount" in summary["flags"]
    assert "not stated" in summary["headline"] or "sprain" in summary["headline"]


# --- service end to end ---

def test_ingest_trusted_claim():
    service = ClaimSynthesisService()
    claim = service.ingest_claim(_doc())
    assert claim["status"] == "trusted"
    assert claim["confidence"] == 1.0
    assert service.review_queue("tenant_acme") == []


def test_ingest_low_confidence_claim_is_queued():
    service = ClaimSynthesisService()
    claim = service.ingest_claim(_doc(
        "CLM-2", narrative="Maria Garcia sustained a sprain to the wrist."))
    assert claim["status"] == "queued_for_review"
    queue = service.review_queue("tenant_acme")
    assert [item["claim_id"] for item in queue] == ["CLM-2"]


def test_review_approve_trusts_claim_and_audits():
    service = ClaimSynthesisService()
    service.ingest_claim(_doc(
        "CLM-3", narrative="Maria Garcia sustained a sprain to the wrist."))
    claim = service.review_claim("CLM-3", "tenant_acme", "approve",
                                 actor="reviewer_1")
    assert claim["status"] == "trusted"
    assert len(service.queue.audit_log) == 1
    assert service.queue.audit_log[0]["action"] == "approve"
    assert service.review_queue("tenant_acme") == []


def test_review_correct_applies_facts():
    service = ClaimSynthesisService()
    service.ingest_claim(_doc(
        "CLM-4", narrative="Maria Garcia sustained a sprain to the wrist."))
    claim = service.review_claim(
        "CLM-4", "tenant_acme", "correct", actor="reviewer_1",
        corrections={"incident_date": "2026-09-14",
                     "claimed_amount": 3400.0})
    assert claim["facts"]["incident_date"]["value"] == "2026-09-14"
    assert claim["facts"]["claimed_amount"]["value"] == 3400.0
    assert claim["status"] == "trusted"
    assert "2026-09-14" in claim["summary"]["details"]


def test_review_reject_marks_claim_rejected():
    service = ClaimSynthesisService()
    service.ingest_claim(_doc(
        "CLM-5", narrative="Maria Garcia sustained a sprain to the wrist."))
    claim = service.review_claim("CLM-5", "tenant_acme", "reject",
                                 actor="reviewer_1", reason="duplicate filing")
    assert claim["status"] == "rejected"
    assert service.queue.audit_log[0]["reason"] == "duplicate filing"


def test_review_errors():
    service = ClaimSynthesisService()
    with pytest.raises(KeyError):
        service.review_claim("CLM-404", "tenant_acme", "approve", "r1")
    service.ingest_claim(_doc(
        "CLM-6", narrative="Maria Garcia sustained a sprain to the wrist."))
    with pytest.raises(ValueError, match="Unknown review action"):
        service.review_claim("CLM-6", "tenant_acme", "escalate", "r1")
    with pytest.raises(ValueError, match="needs corrected fact values"):
        service.review_claim("CLM-6", "tenant_acme", "correct", "r1")
    with pytest.raises(PermissionError):
        service.review_claim("CLM-6", "tenant_beacon", "approve", "r1")


def test_ingest_validates_tenant_and_fields():
    service = ClaimSynthesisService()
    with pytest.raises(ValueError, match="Unknown tenant"):
        service.ingest_claim(_doc(tenant="tenant_nope"))
    with pytest.raises(ValueError, match="missing required field"):
        service.ingest_claim({"claim_id": "CLM-7", "tenant_id": "tenant_acme",
                              "claimant_name": "X", "narrative": ""})


# --- tenant isolation ---

def test_tenant_isolation():
    service = ClaimSynthesisService()
    service.ingest_claim(_doc("CLM-10", tenant="tenant_acme"))
    service.ingest_claim(_doc("CLM-11", tenant="tenant_beacon"))
    assert [c["claim_id"] for c in service.list_claims("tenant_acme")] == ["CLM-10"]
    assert [c["claim_id"] for c in service.list_claims("tenant_beacon")] == ["CLM-11"]
    with pytest.raises(PermissionError):
        service.get_claim("CLM-10", "tenant_beacon")


def test_seeded_documents_cover_both_tenants_and_review_queue():
    service = ClaimSynthesisService()
    for document in generate_documents():
        service.ingest_claim(document)
    assert service.store.count() == 27
    queued = (len(service.review_queue("tenant_acme"))
              + len(service.review_queue("tenant_beacon")))
    assert queued == 3  # the three deliberately incomplete documents


# --- HTTP API ---

@pytest.fixture
def api_server():
    service = ClaimSynthesisService()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, service
    server.shutdown()
    server.server_close()


def _request(base, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_api_ingest_get_review_flow(api_server):
    base, service = api_server
    status, body = _request(base, "POST", "/claims", _doc("CLM-20"))
    assert status == 201
    assert body["status"] == "trusted"
    status, body = _request(base, "GET", "/claims/CLM-20?tenant_id=tenant_acme")
    assert status == 200
    assert body["claim_id"] == "CLM-20"
    status, body = _request(base, "GET", "/claims/CLM-20?tenant_id=tenant_beacon")
    assert status == 403  # cross-tenant read is refused
    status, body = _request(base, "GET", "/claims?tenant_id=tenant_acme")
    assert status == 200
    assert [c["claim_id"] for c in body["claims"]] == ["CLM-20"]


def test_api_review_queue_and_decision(api_server):
    base, service = api_server
    _request(base, "POST", "/claims", _doc(
        "CLM-21", narrative="Maria Garcia sustained a sprain to the wrist."))
    status, body = _request(base, "GET", "/review-queue?tenant_id=tenant_acme")
    assert status == 200
    assert [item["claim_id"] for item in body["queue"]] == ["CLM-21"]
    status, body = _request(base, "POST", "/claims/CLM-21/review", {
        "tenant_id": "tenant_acme", "action": "correct",
        "actor": "reviewer_1",
        "corrections": {"incident_date": "2026-09-14"}})
    assert status == 200
    assert body["status"] == "trusted"
    status, body = _request(base, "GET", "/review-queue?tenant_id=tenant_acme")
    assert body["queue"] == []
