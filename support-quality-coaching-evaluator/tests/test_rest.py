"""Tests for KB retrieval, coaching plans, simulations, evaluation, data."""

from support_quality import (
    CASES, KB_ARTICLES, KnowledgeRetriever, RuleBasedJudge,
    build_coaching_plan, SimulationSession, compare_prompts,
    evaluate_offline, check_dataset,
)
import pytest


def _case(case_id):
    return next(c for c in CASES if c.case_id == case_id)


# ------------------------------------------------------------ retrieval

def test_refund_query_returns_refund_article_first():
    hits = KnowledgeRetriever().retrieve("when will my refund arrive", k=3)
    assert hits
    assert hits[0].article_id == "kb-refund-timeline"
    assert hits[0].score > 0


def test_cancellation_query_returns_cancellation_article():
    hits = KnowledgeRetriever().retrieve("cancel within 48 hours full refund", k=2)
    assert hits[0].article_id == "kb-cancel-48h"


def test_empty_query_returns_no_hits():
    assert KnowledgeRetriever().retrieve("", k=3) == []


def test_hits_carry_citations():
    hits = KnowledgeRetriever().retrieve("host payout held", k=1)
    assert hits[0].snippet
    assert hits[0].title


# ------------------------------------------------------------- coaching

def test_coaching_plan_targets_weakest_criterion():
    result = RuleBasedJudge("v1").grade(_case("case-002"))
    plan = build_coaching_plan(result)
    assert plan.drills
    assert plan.drills[0]["criterion"] in ("Accuracy", "Policy compliance",
                                           "Resolution")
    for drill in plan.drills:
        assert drill["target_score"] == 2
        assert drill["kb_article"]
        assert drill["practice_scenario"]


def test_good_case_plan_has_no_drills():
    result = RuleBasedJudge("v1").grade(_case("case-001"))
    plan = build_coaching_plan(result)
    assert plan.drills == []
    assert len(plan.strengths) == 5


# ----------------------------------------------------------- simulation

def test_simulation_scores_a_good_reply_high():
    session = SimulationSession("sim-unsafe-stay")
    result = session.reply(
        "I'm really sorry — your safety comes first. I've escalated this "
        "to our safety team right now and I can help you rebook somewhere "
        "safe tonight.")
    assert result.passed
    report = session.finish()
    assert report.mean_overall >= 1.4
    assert report.coaching_plan is not None


def test_simulation_flags_a_bad_reply():
    session = SimulationSession("sim-unsafe-stay")
    result = session.reply("Please stay there and wait for someone to come.")
    assert not result.passed
    assert result.scores["policy_compliance"] == 0


def test_unknown_scenario_rejected():
    with pytest.raises(ValueError):
        SimulationSession("sim-does-not-exist")


def test_empty_session_cannot_finish():
    session = SimulationSession("sim-payout-hold")
    with pytest.raises(ValueError):
        session.finish()


# ----------------------------------------------------------- evaluation

def test_offline_agreement_is_reported():
    report = evaluate_offline(RuleBasedJudge("v1"))
    assert report.n_cases == len(CASES)
    assert 0.0 <= report.agreement <= 1.0
    assert report.mean_abs_error >= 0.0
    assert set(report.per_criterion_agreement) == {
        "accuracy", "empathy", "policy_compliance", "resolution", "clarity"}


def test_prompt_ab_compares_both_versions():
    rows = compare_prompts()
    assert [r.prompt_version for r in rows] in (["v1", "v2"], ["v2", "v1"])
    assert all(r.n_cases == len(CASES) for r in rows)


def test_empty_case_list_rejected():
    with pytest.raises(ValueError):
        evaluate_offline(RuleBasedJudge("v1"), cases=[])


# ----------------------------------------------------------------- data

def test_dataset_is_complete():
    assert check_dataset() == []


def test_kb_and_cases_are_nonempty():
    assert len(KB_ARTICLES) >= 5
    assert len(CASES) >= 5
