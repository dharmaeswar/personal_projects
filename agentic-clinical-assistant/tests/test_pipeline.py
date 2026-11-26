"""Tests for the interoperability data pipeline."""

from clinical_agent.pipeline import Pipeline, build_features, validate_record


def _record(patient="P-1001", rtype="Observation", when="2026-11-20",
            summary="blood pressure 120/80"):
    return {"patient_id": patient, "resource_type": rtype,
            "recorded_at": when, "summary": summary}


def test_validate_record_accepts_known_types():
    assert validate_record(_record()) == []


def test_validate_record_rejects_missing_and_unknown():
    errors = validate_record({"patient_id": "P-1001"})
    assert "missing resource_type" in errors
    assert "missing recorded_at" in errors
    assert "unknown resource_type" in validate_record(
        _record(rtype="AllergyIntolerance"))


def test_build_features_counts_by_type():
    records = [_record(), _record(rtype="MedicationRequest"),
               _record(rtype="MedicationRequest", when="2026-11-21")]
    features = build_features(records)
    assert features["P-1001"]["observation_count"] == 1
    assert features["P-1001"]["medication_count"] == 2


def test_pipeline_loads_valid_and_reports_rejects():
    pipeline = Pipeline()
    report = pipeline.run([
        _record(),
        _record(rtype="MedicationRequest", when="2026-11-21"),
        {"patient_id": "P-1001"},  # invalid: missing fields
        _record(),  # duplicate of the first record
    ])
    assert report["received"] == 4
    assert report["loaded"] == 2
    assert report["rejected"] == 1
    assert report["duplicates"] == 1
    assert pipeline.vector_store.count() == 2
    assert pipeline.feature_store.get("P-1001")["observation_count"] == 1


def test_pipeline_search_and_features_after_load():
    pipeline = Pipeline()
    pipeline.run([_record(summary="diabetes follow-up care plan")])
    results = pipeline.vector_store.search(
        "diabetes follow-up",
        metadata_filter={"patient_id": "P-1001"})
    assert results and results[0][0]["metadata"]["resource_type"] == "Observation"
    assert pipeline.feature_store.entities() == ["P-1001"]
