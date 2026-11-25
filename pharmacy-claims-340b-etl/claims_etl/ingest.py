"""Ingest the four Wellpartner source feeds.

Each parser normalises one source format to typed records and reports
malformed rows instead of crashing, so a bad feed file never kills a load:
- pharmacy claims: CSV
- 340B TPA captures: XML
- covered-entity eligibility: fixed-width flat file
- drug inventory / pricing: JSON (NDC -> unit price)
"""

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_claims_csv(path):
    """Return (claims, malformed) for a pharmacy-claims CSV file."""
    claims, malformed = [], []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                claims.append({
                    "claim_id": row["claim_id"].strip(),
                    "patient_id": row["patient_id"].strip(),
                    "ndc": row["ndc"].strip(),
                    "drug_name": row["drug_name"].strip(),
                    "quantity": int(row["quantity"]),
                    "days_supply": int(row["days_supply"]),
                    "fill_date": row["fill_date"].strip(),
                    "pharmacy_id": row["pharmacy_id"].strip(),
                    "prescriber_id": row["prescriber_id"].strip(),
                    "amount": float(row["amount"]),
                })
            except (KeyError, ValueError, AttributeError) as exc:
                malformed.append({"row": row, "error": str(exc)})
    return claims, malformed


def parse_tpa_xml(path):
    """Return (captures, malformed) for a 340B TPA capture XML file.

    Each capture is keyed by claim_id so validation can cross-check that
    the TPA captured the claim.
    """
    captures, malformed = [], []
    tree = ET.parse(path)
    for elem in tree.getroot().findall("capture"):
        try:
            captures.append({
                "tpa_id": elem.findtext("tpa_id").strip(),
                "claim_id": elem.findtext("claim_id").strip(),
                "patient_id": elem.findtext("patient_id").strip(),
                "program": elem.findtext("program").strip(),
                "capture_date": elem.findtext("capture_date").strip(),
            })
        except AttributeError as exc:
            malformed.append({"element": ET.tostring(elem, encoding="unicode"),
                              "error": str(exc)})
    return captures, malformed


def parse_eligibility_flat(path):
    """Parse a fixed-width eligibility file.

    Layout: patient_id (10) | name (20) | eligible flag (1, Y/N) |
    start date (10, YYYY-MM-DD) | end date (10, YYYY-MM-DD).
    Returns {patient_id: record}.
    """
    eligibility = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        eligibility[line[0:10].strip()] = {
            "patient_id": line[0:10].strip(),
            "name": line[10:30].strip(),
            "eligible": line[30:31].strip(),
            "start_date": line[31:41].strip(),
            "end_date": line[41:51].strip(),
        }
    return eligibility


def parse_pricing_json(path):
    """Return {ndc: {'drug': str, 'unit_price': float}}."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {ndc: {"drug": info["drug"], "unit_price": float(info["unit_price"])}
            for ndc, info in raw.items()}
