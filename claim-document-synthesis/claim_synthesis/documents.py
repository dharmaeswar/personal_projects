"""Seeded synthetic claim documents and tenant registry.

All data is synthetic and seeded for reproducibility. No real claimant,
medical, or insurance data is used, and nothing here is a claim about
any real company or claim.
"""
from __future__ import annotations

import random

TENANTS = {
    "tenant_acme": "Acme Mutual Insurance",
    "tenant_beacon": "Beacon Casualty Group",
}

INJURIES = ("fracture", "sprain", "laceration", "burn", "concussion", "strain")
BODY_PARTS = ("knee", "shoulder", "back", "wrist", "ankle", "elbow", "hip")
PROVIDERS = ("Riverside General Hospital", "Northside Orthopedics",
             "Lakeside Urgent Care", "Downtown Physical Therapy")
FIRST_NAMES = ("Maria", "James", "Priya", "Robert", "Aisha", "Daniel",
               "Sofia", "Michael", "Elena", "David")
LAST_NAMES = ("Garcia", "Chen", "Patel", "Johnson", "Kim", "Nguyen",
              "Rossi", "Smith", "Kowalski", "Brown")


def _narrative(rng: random.Random, injury: str, body_part: str, provider: str,
               incident_date: str, amount: int, claimant: str) -> str:
    templates = [
        ("On {date}, {name} sustained a {injury} to the {part} in a workplace "
         "incident. Treated at {provider}. Total claimed amount ${amount}."),
        ("{name} reports a {injury} of the {part} from an incident on {date}. "
         "Care was provided at {provider}. Claimed expenses total ${amount}."),
        ("Claimant {name} was treated at {provider} for a {injury} to the "
         "{part} following an incident dated {date}. Amount claimed: ${amount}."),
    ]
    return rng.choice(templates).format(
        date=incident_date, name=claimant, injury=injury, part=body_part,
        provider=provider, amount=f"{amount:,}")


def generate_documents(count: int = 24, seed: int = 42) -> list[dict]:
    """Generate seeded synthetic claim documents across two tenants."""
    rng = random.Random(seed)
    documents: list[dict] = []
    for i in range(count):
        tenant = "tenant_acme" if i % 2 == 0 else "tenant_beacon"
        injury = rng.choice(INJURIES)
        body_part = rng.choice(BODY_PARTS)
        provider = rng.choice(PROVIDERS)
        claimant = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        month = rng.randint(1, 10)
        day = rng.randint(1, 28)
        incident_date = f"2026-{month:02d}-{day:02d}"
        amount = rng.choice([1250, 3400, 8750, 15200, 24900, 42100])
        documents.append({
            "claim_id": f"CLM-{1000 + i}",
            "tenant_id": tenant,
            "claimant_name": claimant,
            "submitted_date": f"2026-11-{rng.randint(1, 14):02d}",
            "narrative": _narrative(rng, injury, body_part, provider,
                                    incident_date, amount, claimant),
        })
    # Deliberately incomplete documents: missing date, missing amount,
    # and an unknown injury wording, so the review queue is exercised.
    documents.append({
        "claim_id": "CLM-9001", "tenant_id": "tenant_acme",
        "claimant_name": "Test Incomplete",
        "submitted_date": "2026-11-10",
        "narrative": "Maria Garcia sustained a sprain to the wrist. Treated at "
                     "Riverside General Hospital.",
    })
    documents.append({
        "claim_id": "CLM-9002", "tenant_id": "tenant_beacon",
        "claimant_name": "Test No Amount",
        "submitted_date": "2026-11-11",
        "narrative": "James Chen reports a fracture of the ankle from an incident "
                     "on 2026-09-14. Care was provided at Northside Orthopedics.",
    })
    documents.append({
        "claim_id": "CLM-9003", "tenant_id": "tenant_acme",
        "claimant_name": "Test Unknown Injury",
        "submitted_date": "2026-11-12",
        "narrative": "Priya Patel was treated for a mysterious ailment after an "
                     "incident on 2026-08-02. Amount claimed: $5,400.",
    })
    return documents
