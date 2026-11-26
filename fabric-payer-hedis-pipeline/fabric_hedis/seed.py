"""Seeded synthetic payer data for the Fabric payer file exchange demo.

All members, claims, labs and screenings are invented and deterministic
(seed 42). No real member, patient, claim or PHI data is used, and nothing
here describes any real insurer, payer, vendor or person.
"""

import csv
import hashlib
import json
import random
from pathlib import Path

PLANS = ["Medicare Advantage", "Medicaid", "Commercial"]
DIAG_CODES = ["E11.9", "I10", "J45.909", "M54.5", "N18.3", "Z00.00"]
PROCEDURES = ["99213", "99214", "80053", "83036", "77067", "45378", "82270"]

MEMBER_COLUMNS = ["member_id", "sex", "age", "plan", "diabetes",
                  "hypertension", "enrollment_start", "enrollment_end"]
CLAIM_COLUMNS = ["claim_id", "member_id", "service_date", "diag_code",
                 "procedure_code", "billed_amount", "adjustment",
                 "paid_amount", "source_file"]
LAB_COLUMNS = ["member_id", "test", "result", "result_date"]
SCREENING_COLUMNS = ["member_id", "screening_type", "screening_date"]


def _member(i):
    age = 20 + (i * 7) % 61  # deterministic spread, 20..80
    return {
        "member_id": "M%04d" % i,
        "sex": "F" if i % 2 == 0 else "M",
        "age": age,
        "plan": PLANS[i % 3],
        "diabetes": "Y" if i % 3 == 0 else "N",
        "hypertension": "Y" if i % 2 == 0 else "N",
        "enrollment_start": "2025-01-01",
        "enrollment_end": "2026-12-31",
    }


def build_seed_data(seed=42):
    """Return dict of table name -> list of row dicts (all strings)."""
    rng = random.Random(seed)
    members = [_member(i) for i in range(1, 61)]

    labs = []
    screenings = []
    for m in members:
        i = int(m["member_id"][1:])
        age = m["age"]
        if m["diabetes"] == "Y":
            hba1c = round(6.5 + (i % 10) * 0.3, 1)  # 6.5..9.2; <8.0 iff i%10<=4
            labs.append({"member_id": m["member_id"], "test": "HbA1c",
                         "result": str(hba1c), "result_date": "2026-09-15"})
        if m["hypertension"] == "Y":
            systolic = 118 + (i % 6) * 6    # 118..148; <140 iff i%6<=3
            diastolic = 72 + (i % 4) * 4    # 72..84, always <90
            labs.append({"member_id": m["member_id"], "test": "BP",
                         "result": "%d/%d" % (systolic, diastolic),
                         "result_date": "2026-09-20"})
        if m["sex"] == "F" and 40 <= age <= 74 and i % 4 != 0:
            screenings.append({"member_id": m["member_id"],
                               "screening_type": "mammogram",
                               "screening_date": "2026-03-10"})
        if 45 <= age <= 75:
            if i % 5 != 0:
                screenings.append({"member_id": m["member_id"],
                                   "screening_type": "colonoscopy",
                                   "screening_date": "2021-06-01"})
            else:
                screenings.append({"member_id": m["member_id"],
                                   "screening_type": "FIT",
                                   "screening_date": "2026-08-05"})

    claims = []
    for m in members:
        for k in range(3):
            billed = round(rng.uniform(120.0, 2400.0), 2)
            adjustment = round(rng.uniform(0.0, 50.0), 2)
            paid = round(billed - adjustment, 2)
            day = rng.randint(1, 28)
            month = rng.choice(["09", "10"])
            claims.append({
                "claim_id": "C%05d" % (len(claims) + 1),
                "member_id": m["member_id"],
                "service_date": "2026-%s-%02d" % (month, day),
                "diag_code": rng.choice(DIAG_CODES),
                "procedure_code": rng.choice(PROCEDURES),
                "billed_amount": "%.2f" % billed,
                "adjustment": "%.2f" % adjustment,
                "paid_amount": "%.2f" % paid,
                "source_file": "claims_2026-10.csv",
            })

    # Six planted defects in the inbound claims feed (the pipeline must
    # quarantine all six; they are not part of the clean 180).
    defects = [
        dict(claims[0], paid_amount="%.2f" % (float(claims[0]["paid_amount"]) + 1.00)),
        dict(claims[1], claim_id="C99991", paid_amount="-25.00"),
        dict(claims[2], claim_id="C99992", member_id="M9999"),
        dict(claims[3], claim_id="C99993", service_date="2027-01-15"),
        dict(claims[4], claim_id="C99994", diag_code="Z99.99"),
        dict(claims[5], claim_id="C99995", paid_amount="999.99"),
    ]
    # The first defect is a late duplicate copy of C00001 with a changed
    # paid amount: dedup keeps the latest copy, which then fails the
    # arithmetic check and is quarantined as paid_amount_mismatch.
    claims.extend(defects)
    return {"members": members, "claims": claims, "labs": labs,
            "screenings": screenings}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_inbound_files(out_dir, seed=42):
    """Write the four payer files plus a manifest into out_dir (SFTP inbox).

    Returns the manifest dict {file: {"rows": n, "sha256": hex}}.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = build_seed_data(seed)
    files = [("members_2026-10.csv", MEMBER_COLUMNS, data["members"]),
             ("claims_2026-10.csv", CLAIM_COLUMNS, data["claims"]),
             ("labs_2026-10.csv", LAB_COLUMNS, data["labs"]),
             ("screenings_2026-10.csv", SCREENING_COLUMNS, data["screenings"])]
    manifest = {}
    for name, columns, rows in files:
        path = out / name
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        manifest[name] = {"rows": len(rows), "sha256": _sha256(path)}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
