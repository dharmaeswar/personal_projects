"""Tests for the ITA candidate-funnel module (lakehouse/recruiting.py)."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.recruiting import (
    build_funnel_model,
    build_funnel_view,
    build_requisition_view,
    check_funnel_reconciliation,
    generate_recruiting,
    generate_recruiting_events,
    load_assessment_batch,
    quarantine_applications,
    quarantine_assessments,
    quarantine_hires,
    quarantine_interviews,
    quarantine_offers,
    run_recruiting_stream,
    validate_applications,
    validate_assessments,
    validate_hires,
    validate_interviews,
    validate_offers,
)


@pytest.fixture(scope="module")
def data():
    return generate_recruiting()


def test_domain_shapes(data):
    assert len(data["requisitions"]) == 30
    assert data["requisitions"]["req_id"].is_unique
    assert len(data["candidates"]) == 200
    assert data["candidates"]["candidate_id"].is_unique
    # 300 base applications + 2 planted duplicate deliveries.
    assert len(data["applications"]) == 302
    assert len(data["assessments"]) > 150
    assert len(data["interviews"]) > 50
    assert len(data["offers"]) > 10
    assert len(data["hires"]) > 5


def test_application_checks_fail_as_designed(data):
    results = validate_applications(
        data["applications"], data["requisitions"], data["candidates"]
    )
    by_name = {r.name: r for r in results}
    assert by_name["completeness"].passed is False  # 2 null candidate_ids
    assert by_name["uniqueness:application_id"].passed is False  # 2 duplicates
    assert by_name["fk:req_id->req_id"].passed is True
    assert by_name["fk:candidate_id->candidate_id"].passed is False  # CAND-9999


def test_assessment_checks_fail_as_designed(data):
    results = validate_assessments(data["assessments"], data["applications"])
    by_name = {r.name: r for r in results}
    assert by_name["range:score"].passed is False  # planted score 142
    assert by_name["uniqueness:assessment_id"].passed is True


def test_interview_date_rule_fails_as_designed(data):
    results = validate_interviews(data["interviews"], data["applications"])
    by_name = {r.name: r for r in results}
    assert by_name["interview_after_application"].passed is False  # 1 early interview


def test_offer_and_hire_checks_fail_as_designed(data):
    offer_results = validate_offers(
        data["offers"], data["applications"], data["requisitions"]
    )
    by_name = {r.name: r for r in offer_results}
    assert by_name["fk:req_id->req_id"].passed is False  # REQ-999
    hire_results = validate_hires(
        data["hires"], data["offers"], data["applications"]
    )
    by_name = {r.name: r for r in hire_results}
    assert by_name["fk:offer_id->offer_id"].passed is False  # OFR-99999


def test_quarantine_counts(data):
    silver_app, quar_app = quarantine_applications(
        data["applications"], data["requisitions"], data["candidates"]
    )
    # 5 bad application rows: 2 duplicates (2nd copies), 2 nulls, 1 unknown candidate.
    assert len(quar_app) == 5
    assert len(silver_app) == 297
    silver_asm, quar_asm = quarantine_assessments(
        data["assessments"], data["applications"]
    )
    assert len(quar_asm) == 1  # the out-of-range score
    silver_int, quar_int = quarantine_interviews(
        data["interviews"], data["applications"]
    )
    assert len(quar_int) == 1  # the early interview
    silver_ofr, quar_ofr = quarantine_offers(
        data["offers"], data["applications"], data["requisitions"]
    )
    assert len(quar_ofr) == 1  # the unknown req
    silver_hir, quar_hir = quarantine_hires(
        data["hires"], data["offers"], data["applications"]
    )
    assert len(quar_hir) == 1  # the hire with no offer


def test_funnel_model_shape_and_stages(data):
    silver_app, _ = quarantine_applications(
        data["applications"], data["requisitions"], data["candidates"]
    )
    silver_asm, _ = quarantine_assessments(
        data["assessments"], data["applications"]
    )
    silver_int, _ = quarantine_interviews(
        data["interviews"], data["applications"]
    )
    silver_ofr, _ = quarantine_offers(
        data["offers"], data["applications"], data["requisitions"]
    )
    silver_hir, _ = quarantine_hires(
        data["hires"], data["offers"], data["applications"]
    )
    funnel = build_funnel_model(
        silver_app, data["requisitions"], silver_asm, silver_int, silver_ofr, silver_hir
    )
    assert len(funnel) == 297
    assert set(funnel["stage"].unique()) <= {
        "Applied", "Assessed", "Interviewed", "Offered", "Hired"
    }
    # Stage label always matches the furthest flag set for that row.
    assert (funnel.loc[funnel["hired"], "stage"] == "Hired").all()
    assert (funnel.loc[funnel["offered"] & ~funnel["hired"], "stage"] == "Offered").all()
    # Days to hire is positive for every hire.
    assert (funnel.loc[funnel["hired"], "days_to_hire"] > 0).all()


def test_funnel_views_reconcile(data):
    silver_app, _ = quarantine_applications(
        data["applications"], data["requisitions"], data["candidates"]
    )
    silver_asm, _ = quarantine_assessments(
        data["assessments"], data["applications"]
    )
    silver_int, _ = quarantine_interviews(
        data["interviews"], data["applications"]
    )
    silver_ofr, _ = quarantine_offers(
        data["offers"], data["applications"], data["requisitions"]
    )
    silver_hir, _ = quarantine_hires(
        data["hires"], data["offers"], data["applications"]
    )
    funnel = build_funnel_model(
        silver_app, data["requisitions"], silver_asm, silver_int, silver_ofr, silver_hir
    )
    funnel_view = build_funnel_view(funnel)
    req_view = build_requisition_view(funnel, data["requisitions"])
    assert len(funnel_view) == 5  # one row per department
    assert len(req_view) == 30  # one row per requisition
    assert int(req_view["hires"].sum()) == int(funnel["hired"].sum())
    recon = check_funnel_reconciliation(
        funnel, silver_asm, silver_int, silver_ofr, silver_hir,
        funnel_view, req_view,
    )
    assert recon.passed is True


def test_stream_exactly_once():
    events = generate_recruiting_events()
    assert len(events) == 155  # 150 + 3 duplicates + 2 late
    result = run_recruiting_stream(events)
    assert result["total_arrived"] == 155
    assert len(result["accepted"]) == 150
    assert len(result["duplicates"]) == 3
    assert len(result["late"]) == 2


def test_assessment_batch_dedup(data):
    loaded, duplicates = load_assessment_batch(data["assessments"])
    assert len(loaded) == len(data["assessments"])
    assert len(duplicates) == 0  # no duplicate assessment_ids in the fixture
    doubled = pd.concat([data["assessments"], data["assessments"].iloc[[0]]])
    loaded2, duplicates2 = load_assessment_batch(doubled)
    assert len(duplicates2) == 1
    assert len(loaded2) == len(data["assessments"])
