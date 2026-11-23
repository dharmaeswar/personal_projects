"""Tests for the workforce data-architecture module (lakehouse/workforce.py)."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.workforce import (
    build_analytics_view,
    build_operational_view,
    build_unified_model,
    check_unified_reconciliation,
    evaluate_genai_assist,
    generate_workforce,
    generate_workforce_events,
    load_engagement_batch,
    quarantine_candidates,
    quarantine_engagement,
    quarantine_interviews,
    quarantine_moves,
    quarantine_offers,
    run_workforce_stream,
    tune_query_demo,
    validate_candidates,
    validate_engagement,
    validate_interviews,
    validate_moves,
    validate_offers,
)


@pytest.fixture(scope="module")
def data():
    return generate_workforce()


def test_domain_shapes(data):
    assert len(data["roles"]) == 20
    assert data["roles"]["role_id"].is_unique
    assert len(data["employees"]) == 60
    assert len(data["requisitions"]) == 15
    assert data["requisitions"]["req_id"].is_unique
    # 90 base candidates + 2 planted duplicate deliveries.
    assert len(data["candidates"]) == 92
    assert len(data["interviews"]) >= 30
    assert len(data["offers"]) >= 5
    assert len(data["moves"]) == 12
    assert len(data["engagement"]) == 120


def test_every_violation_type_is_caught(data):
    cand_checks = validate_candidates(data["candidates"], data["requisitions"])
    assert any(not c.passed for c in cand_checks)
    assert any(c.name == "uniqueness:candidate_id" for c in cand_checks if not c.passed)
    int_checks = validate_interviews(data["interviews"], data["candidates"])
    assert any(
        c.name == "interview_after_application" and not c.passed
        for c in int_checks
    )
    off_checks = validate_offers(
        data["offers"], data["candidates"], data["interviews"]
    )
    assert any(
        c.name == "offer_has_interview" and not c.passed for c in off_checks
    )
    move_checks = validate_moves(data["moves"], data["employees"], data["roles"])
    assert any(
        c.name == "move_after_hire" and not c.passed for c in move_checks
    )
    eng_checks = validate_engagement(data["engagement"], data["employees"])
    assert any(
        c.name == "range:score" and not c.passed for c in eng_checks
    )


def test_quarantine_counts(data):
    silver_c, quar_c = quarantine_candidates(data["candidates"], data["requisitions"])
    # 2 duplicate deliveries + 1 null req + 1 unknown req = 4 quarantined.
    assert len(quar_c) == 4
    assert len(silver_c) == 88
    assert silver_c["candidate_id"].is_unique
    _, quar_i = quarantine_interviews(data["interviews"], data["candidates"])
    assert len(quar_i) == 1
    _, quar_o = quarantine_offers(data["offers"], data["candidates"], data["interviews"])
    assert len(quar_o) == 1
    _, quar_m = quarantine_moves(data["moves"], data["employees"], data["roles"])
    assert len(quar_m) == 1
    _, quar_e = quarantine_engagement(data["engagement"], data["employees"])
    assert len(quar_e) == 1


def test_quarantine_reasons_named(data):
    _, quar_c = quarantine_candidates(data["candidates"], data["requisitions"])
    assert quar_c["quarantine_reason"].str.len().gt(0).all()
    _, quar_i = quarantine_interviews(data["interviews"], data["candidates"])
    assert "interview_after_application" in quar_i["quarantine_reason"].iloc[0]
    _, quar_e = quarantine_engagement(data["engagement"], data["employees"])
    assert "range:score" in quar_e["quarantine_reason"].iloc[0]


def test_unified_model_contents(data):
    silver_c, _ = quarantine_candidates(data["candidates"], data["requisitions"])
    silver_i, _ = quarantine_interviews(data["interviews"], data["candidates"])
    silver_o, _ = quarantine_offers(data["offers"], data["candidates"], data["interviews"])
    unified = build_unified_model(
        data["requisitions"], data["roles"], silver_c, silver_i, silver_o
    )
    assert len(unified) == 15
    assert unified["candidates"].sum() == len(silver_c)
    assert (unified["hires"] <= unified["candidates"]).all()
    assert (unified["offers"] <= unified["candidates"]).all()
    filled = unified[unified["status"] == "filled"]
    assert filled["time_to_fill_days"].notna().all()
    assert (filled["time_to_fill_days"] > 0).all()


def test_view_reconciliation(data):
    silver_c, _ = quarantine_candidates(data["candidates"], data["requisitions"])
    silver_i, _ = quarantine_interviews(data["interviews"], data["candidates"])
    silver_o, _ = quarantine_offers(data["offers"], data["candidates"], data["interviews"])
    silver_m, _ = quarantine_moves(data["moves"], data["employees"], data["roles"])
    silver_e, _ = quarantine_engagement(data["engagement"], data["employees"])
    unified = build_unified_model(
        data["requisitions"], data["roles"], silver_c, silver_i, silver_o
    )
    analytics = build_analytics_view(unified, silver_e, silver_m, data["employees"])
    operational = build_operational_view(unified)
    assert len(operational) == 15
    assert analytics["requisitions"].sum() == 15
    recon = check_unified_reconciliation(unified, silver_c, analytics)
    assert recon.passed


def test_streaming_exactly_once():
    events = generate_workforce_events()
    result = run_workforce_stream(events)
    assert result["total_arrived"] == 125
    assert len(result["accepted"]) == 120
    assert len(result["late"]) == 2
    assert len(result["duplicates"]) == 3


def test_batch_dedup(data):
    loaded, dupes = load_engagement_batch(data["engagement"])
    assert len(loaded) + len(dupes) == len(data["engagement"])
    assert loaded["survey_id"].is_unique


def test_genai_assist_evaluation():
    result = evaluate_genai_assist()
    assert result["real_llm_call"] is False
    assert result["rules_proposed"] == 8
    assert result["rules_true"] == 5
    assert result["precision"] == 0.625
    assert result["violation_types_caught"] == 5
    assert result["recall"] == round(5 / 7, 3)
    assert result["spurious_rules_rejected"] == 3


def test_tuning_results_match(data):
    silver_c, _ = quarantine_candidates(data["candidates"], data["requisitions"])
    tuning = tune_query_demo(silver_c, data["requisitions"])
    assert tuning["rows"] >= 50000
    assert tuning["results_match"] is True
    assert tuning["speedup"] > 1


def test_determinism():
    first = generate_workforce()
    second = generate_workforce()
    for key in first:
        pd.testing.assert_frame_equal(first[key], second[key])
