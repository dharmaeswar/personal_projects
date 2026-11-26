"""Data pipeline: ingest interoperability records into the stores.

Mimics the data foundation behind an LLM-powered clinical product: raw
interoperability records (FHIR-shaped JSON, synthetic and local) are
validated, de-duplicated, turned into patient features, indexed for
retrieval, and loaded into the feature store and vector store. Every stage
reports counts and rejects, so a bad feed is visible instead of silent.

All data is synthetic. No real patients, no real clinical records.
"""

from .phi import redact
from .vector_store import FeatureStore, VectorStore

REQUIRED_FIELDS = ("patient_id", "resource_type", "recorded_at")


def validate_record(record):
    """Return a list of validation errors; empty means the record is valid."""
    errors = []
    if not isinstance(record, dict):
        return ["record is not an object"]
    for field in REQUIRED_FIELDS:
        if not record.get(field):
            errors.append(f"missing {field}")
    if record.get("resource_type") not in (
        "Observation",
        "MedicationRequest",
        "Condition",
        "Encounter",
    ):
        errors.append("unknown resource_type")
    return errors


def build_features(records):
    """Aggregate validated records into per-patient feature dicts."""
    features = {}
    for record in records:
        patient = features.setdefault(
            record["patient_id"],
            {"observation_count": 0, "medication_count": 0,
             "condition_count": 0, "encounter_count": 0},
        )
        key = record["resource_type"].lower().replace("medicationrequest", "medication")
        patient[f"{key}_count"] = patient.get(f"{key}_count", 0) + 1
    return features


class Pipeline:
    """Validate -> dedupe -> feature/store load, with a run report."""

    def __init__(self):
        self.vector_store = VectorStore()
        self.feature_store = FeatureStore()

    def run(self, records, version="v1"):
        report = {"received": len(records), "loaded": 0,
                  "rejected": 0, "duplicates": 0, "errors": []}
        seen = set()
        valid = []
        for record in records:
            errors = validate_record(record)
            if errors:
                report["rejected"] += 1
                report["errors"].append(
                    {"record": redact(str(record))[:120], "errors": errors})
                continue
            key = (record["patient_id"], record["resource_type"],
                   record["recorded_at"])
            if key in seen:
                report["duplicates"] += 1
                continue
            seen.add(key)
            valid.append(record)
        for record in valid:
            text = (
                f"{record['resource_type']} for {record['patient_id']} "
                f"recorded {record['recorded_at']}: "
                f"{record.get('summary', '')}"
            )
            self.vector_store.upsert(
                f"{record['patient_id']}-{record['resource_type']}"
                f"-{record['recorded_at']}",
                text,
                metadata={"patient_id": record["patient_id"],
                          "resource_type": record["resource_type"]},
            )
        for patient_id, feats in build_features(valid).items():
            self.feature_store.put(patient_id, feats, version)
        report["loaded"] = len(valid)
        return report
