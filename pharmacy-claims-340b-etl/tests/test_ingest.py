"""Tests for the four source-format parsers."""

from pathlib import Path

from claims_etl import ingest

DATA = Path(__file__).resolve().parent.parent / "data"


def test_parse_claims_csv():
    claims, malformed = ingest.parse_claims_csv(DATA / "pharmacy_claims.csv")
    assert len(claims) == 12
    assert malformed == []
    first = claims[0]
    assert first["claim_id"] == "C1001"
    assert first["quantity"] == 30 and first["amount"] == 45.00
    assert first["fill_date"] == "2026-11-20"


def test_parse_claims_csv_reports_malformed_rows():
    bad = DATA / "bad_claims.csv"
    bad.write_text("claim_id,patient_id,ndc,drug_name,quantity,days_supply,"
                   "fill_date,pharmacy_id,prescriber_id,amount\n"
                   "C9001,P000000001,00093721401,Amoxicillin,xx,30,"
                   "2026-11-20,PH01,DR01,45.00\n", encoding="utf-8")
    try:
        claims, malformed = ingest.parse_claims_csv(bad)
        assert claims == []
        assert len(malformed) == 1
    finally:
        bad.unlink()


def test_parse_tpa_xml():
    captures, malformed = ingest.parse_tpa_xml(DATA / "tpa_340b.xml")
    assert len(captures) == 12
    assert malformed == []
    assert captures[0]["claim_id"] == "C1001"
    assert captures[0]["program"] == "340B"
    assert "C1012" not in {c["claim_id"] for c in captures}


def test_parse_eligibility_flat():
    elig = ingest.parse_eligibility_flat(DATA / "eligibility.txt")
    assert len(elig) == 4
    assert elig["P000000001"]["eligible"] == "Y"
    assert elig["P000000003"]["eligible"] == "N"
    assert elig["P000000004"]["end_date"] == "2026-06-30"
    assert elig["P000000002"]["name"] == "Bob Martinez"


def test_parse_pricing_json():
    pricing = ingest.parse_pricing_json(DATA / "drug_pricing.json")
    assert pricing["00093721401"]["unit_price"] == 1.50
    assert pricing["00781803501"]["unit_price"] == 0.30
    assert pricing["00904123401"]["drug"] == "Atorvastatin"
