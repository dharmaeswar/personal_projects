from clinical_agent.rwd import (
    build_cohort, data_quality, generate_claims, patient_journey,
    treatment_patterns, utilization_summary,
)
from clinical_agent.tools import ToolServer


def test_generate_claims_is_deterministic():
    assert generate_claims() == generate_claims()
    assert generate_claims(seed=7) != generate_claims(seed=42)


def test_generate_claims_shape():
    records = generate_claims(n_patients=5)
    assert records
    for r in records:
        assert r["claim_id"].startswith("C-")
        assert r["claim_type"] in ("medical", "pharmacy")
        assert r["cost"] > 0


def test_build_cohort_by_condition():
    records = generate_claims()
    cohort = build_cohort(records, condition="hypertension")
    assert cohort
    for pid in cohort:
        assert any(r["patient_id"] == pid and r["condition"] == "hypertension" for r in records)


def test_build_cohort_by_drug():
    records = generate_claims()
    cohort = build_cohort(records, drug="metformin")
    assert cohort
    assert cohort == sorted(set(cohort))


def test_patient_journey_is_longitudinal():
    records = generate_claims()
    pid = records[0]["patient_id"]
    journey = patient_journey(records, pid)
    assert journey["n_events"] >= 3
    dates = [e["service_date"] for e in journey["events"]]
    assert dates == sorted(dates)
    assert journey["total_cost"] > 0


def test_patient_journey_unknown_patient():
    journey = patient_journey(generate_claims(), "P-9999")
    assert journey["n_events"] == 0
    assert journey["events"] == []


def test_treatment_patterns_cover_conditions():
    patterns = treatment_patterns(generate_claims())
    assert patterns
    for cond, agg in patterns.items():
        assert agg["n_claims"] > 0
        assert agg["n_patients"] > 0


def test_utilization_summary_totals():
    records = generate_claims()
    summary = utilization_summary(records)
    assert summary["n_claims"] == len(records)
    assert sum(summary["by_claim_type"].values()) == len(records)
    assert summary["total_cost"] > 0


def test_data_quality_passes_on_synthetic_data():
    report = data_quality(generate_claims())
    assert report["completeness_pct"] == 100.0
    assert report["duplicate_claim_ids"] == 0
    assert report["passed"] is True


def test_data_quality_flags_bad_records():
    bad = [{"claim_id": "C-1", "patient_id": "P-1", "service_date": "not-a-date",
            "claim_type": "medical", "condition": "asthma", "cost": -5},
           {"claim_id": "C-1", "patient_id": "", "service_date": "2025-01-01",
            "claim_type": "medical", "condition": "asthma", "cost": 10}]
    report = data_quality(bad)
    assert report["duplicate_claim_ids"] == 1
    assert report["invalid_dates"] == 1
    assert report["negative_costs"] == 1
    assert report["passed"] is False


def test_rwd_tool_via_tool_server():
    server = ToolServer()
    result = server.call("analyze_rwd", condition="hypertension")
    assert result["cohort"]
    assert result["utilization"]["n_claims"] > 0
    assert result["quality"]["passed"] is True
    assert "hypertension" in result["treatment_patterns"]
