"""Real-World Data (RWD) analytics over synthetic claims-like records.

All records are generated locally with a fixed seed. No real patient data,
no real claims, no external datasets. Condition / procedure / drug codes
are simple synthetic labels for demo purposes only -- they are NOT a claim
of ICD-10-CM, CPT/HCPCS, NDC or RxNorm expertise.

Functions:
- generate_claims: deterministic synthetic claims-like records
- build_cohort: filter records into a cohort by condition/procedure/drug
- patient_journey: longitudinal, time-ordered events for one patient
- treatment_patterns: drug/procedure aggregates per condition
- utilization_summary: counts, costs and rates by claim type / month
- data_quality: completeness, duplicate and validity checks
"""

import random
from collections import Counter, defaultdict
from datetime import date, timedelta

CONDITIONS = ["type 2 diabetes", "hypertension", "high cholesterol", "asthma"]
PROCEDURES = ["office visit", "lab panel", "imaging", "vaccination"]
DRUGS = {
    "type 2 diabetes": ["metformin", "glipizide"],
    "hypertension": ["lisinopril", "amlodipine"],
    "high cholesterol": ["atorvastatin"],
    "asthma": ["albuterol inhaler"],
}
_BASE = date(2025, 1, 6)


def generate_claims(n_patients=12, seed=42):
    """Return a deterministic list of synthetic claims-like records."""
    rng = random.Random(seed)
    records = []
    claim_seq = 1
    for idx in range(n_patients):
        patient_id = f"P-{1001 + idx}"
        conditions = rng.sample(CONDITIONS, k=rng.choice([1, 1, 2]))
        start_offset = rng.randint(0, 60)
        n_events = rng.randint(3, 7)
        for ev in range(n_events):
            condition = rng.choice(conditions)
            service_date = _BASE + timedelta(days=start_offset + ev * rng.randint(20, 50))
            if rng.random() < 0.45:
                claim_type = "pharmacy"
                drug = rng.choice(DRUGS[condition])
                procedure = None
                cost = round(rng.uniform(12.0, 180.0), 2)
            else:
                claim_type = "medical"
                drug = None
                procedure = rng.choice(PROCEDURES)
                cost = round(rng.uniform(45.0, 650.0), 2)
            records.append({
                "claim_id": f"C-{claim_seq:04d}",
                "patient_id": patient_id,
                "service_date": service_date.isoformat(),
                "claim_type": claim_type,
                "condition": condition,
                "procedure": procedure,
                "drug": drug,
                "cost": cost,
            })
            claim_seq += 1
    records.sort(key=lambda r: (r["service_date"], r["claim_id"]))
    return records


def build_cohort(records, condition=None, procedure=None, drug=None):
    """Return sorted unique patient_ids matching all given filters."""
    patients = set()
    for r in records:
        if condition and r.get("condition") != condition:
            continue
        if procedure and r.get("procedure") != procedure:
            continue
        if drug and r.get("drug") != drug:
            continue
        patients.add(r["patient_id"])
    return sorted(patients)


def patient_journey(records, patient_id):
    """Longitudinal summary: time-ordered events for one patient."""
    events = sorted(
        [r for r in records if r["patient_id"] == patient_id],
        key=lambda r: (r["service_date"], r["claim_id"]),
    )
    if not events:
        return {"patient_id": patient_id, "events": [], "n_events": 0,
                "conditions": [], "span_days": 0, "total_cost": 0.0}
    dates = [date.fromisoformat(e["service_date"]) for e in events]
    return {
        "patient_id": patient_id,
        "events": events,
        "n_events": len(events),
        "conditions": sorted({e["condition"] for e in events}),
        "span_days": (max(dates) - min(dates)).days,
        "total_cost": round(sum(e["cost"] for e in events), 2),
    }


def treatment_patterns(records):
    """Aggregates: for each condition, drug and procedure counts."""
    by_condition = {}
    grouped = defaultdict(list)
    for r in records:
        grouped[r["condition"]].append(r)
    for condition, rows in sorted(grouped.items()):
        by_condition[condition] = {
            "n_claims": len(rows),
            "n_patients": len({r["patient_id"] for r in rows}),
            "drugs": dict(Counter(r["drug"] for r in rows if r["drug"])),
            "procedures": dict(Counter(r["procedure"] for r in rows if r["procedure"])),
        }
    return by_condition


def utilization_summary(records):
    """Healthcare-utilization aggregates by claim type and month."""
    by_type = Counter(r["claim_type"] for r in records)
    by_month = Counter(r["service_date"][:7] for r in records)
    total_cost = round(sum(r["cost"] for r in records), 2)
    return {
        "n_claims": len(records),
        "n_patients": len({r["patient_id"] for r in records}),
        "by_claim_type": dict(by_type),
        "by_month": dict(sorted(by_month.items())),
        "total_cost": total_cost,
        "avg_cost_per_claim": round(total_cost / len(records), 2) if records else 0.0,
    }


REQUIRED_FIELDS = ["claim_id", "patient_id", "service_date", "claim_type", "condition", "cost"]


def data_quality(records):
    """Completeness / validity checks over claims-like records."""
    total = len(records)
    missing = Counter()
    invalid_dates = 0
    negative_costs = 0
    for r in records:
        for f in REQUIRED_FIELDS:
            if r.get(f) is None or r.get(f) == "":
                missing[f] += 1
        try:
            date.fromisoformat(str(r.get("service_date")))
        except (ValueError, TypeError):
            invalid_dates += 1
        if isinstance(r.get("cost"), (int, float)) and r["cost"] < 0:
            negative_costs += 1
    ids = [r.get("claim_id") for r in records]
    duplicates = len(ids) - len(set(ids))
    completeness = (
        round(100.0 * (1 - sum(missing.values()) / (total * len(REQUIRED_FIELDS))), 2)
        if total else 100.0
    )
    return {
        "n_records": total,
        "completeness_pct": completeness,
        "missing_by_field": dict(missing),
        "duplicate_claim_ids": duplicates,
        "invalid_dates": invalid_dates,
        "negative_costs": negative_costs,
        "passed": duplicates == 0 and invalid_dates == 0 and negative_costs == 0 and completeness == 100.0,
    }
