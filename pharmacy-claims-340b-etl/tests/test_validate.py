"""Tests for the six 340B validation rules."""

from pathlib import Path

from claims_etl import ingest, validate

DATA = Path(__file__).resolve().parent.parent / "data"


def _context():
    claims, _ = ingest.parse_claims_csv(DATA / "pharmacy_claims.csv")
    tpa, _ = ingest.parse_tpa_xml(DATA / "tpa_340b.xml")
    return (claims, ingest.parse_eligibility_flat(DATA / "eligibility.txt"),
            ingest.parse_pricing_json(DATA / "drug_pricing.json"), tpa)


def test_batch_splits_five_valid_seven_quarantined():
    claims, elig, pricing, tpa = _context()
    valid, quarantined = validate.validate_batch(claims, elig, pricing, tpa)
    assert {c["claim_id"] for c in valid} == {
        "C1001", "C1002", "C1003", "C1009", "C1010"}
    assert len(quarantined) == 7


def test_ineligible_patient_quarantined():
    claims, elig, pricing, tpa = _context()
    _, quarantined = validate.validate_batch(claims, elig, pricing, tpa)
    by_id = {q["claim"]["claim_id"]: q["violations"] for q in quarantined}
    assert any("not 340B-eligible" in v for v in by_id["C1004"])
    # C1005: eligibility window ended 2026-06-30, fill is 2026-11-20.
    assert any("not 340B-eligible" in v for v in by_id["C1005"])


def test_duplicate_malformed_ndc_and_utilisation():
    claims, elig, pricing, tpa = _context()
    _, quarantined = validate.validate_batch(claims, elig, pricing, tpa)
    by_id = {q["claim"]["claim_id"]: q["violations"] for q in quarantined}
    assert any("duplicate claim_id" in v for v in by_id["C1001"])
    assert any("11-digit" in v for v in by_id["C1007"])
    assert any("no pricing record" in v for v in by_id["C1007"])
    assert any("quantity 0 is not positive" in v for v in by_id["C1008"])
    assert any("days_supply 120" in v for v in by_id["C1012"])
    assert any("no 340B TPA capture" in v for v in by_id["C1012"])


def test_amount_must_match_pricing():
    claims, elig, pricing, tpa = _context()
    _, quarantined = validate.validate_batch(claims, elig, pricing, tpa)
    by_id = {q["claim"]["claim_id"]: q["violations"] for q in quarantined}
    # 90 x $0.30 = $27.00, but the claim says $30.00.
    assert any("does not match quantity x unit price" in v
               for v in by_id["C1011"])
    # A valid claim passes the amount rule.
    valid, _ = validate.validate_batch(claims, elig, pricing, tpa)
    c1003 = next(c for c in valid if c["claim_id"] == "C1003")
    assert validate.validate_claim(c1003, {
        "eligibility": elig, "pricing": pricing,
        "tpa_claim_ids": {c["claim_id"] for c in tpa},
        "seen_claim_ids": {"C1001", "C1002"}}) == []
