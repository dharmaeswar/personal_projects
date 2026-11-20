import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from ml_platform.decisioning import (
    ACTIONS,
    DecisioningEngine,
    baseline_action,
    generate_members,
    log_decision,
    outcome_report,
    read_decisions,
)
from ml_platform.registry import Registry
from ml_platform.training import train_pipeline

FIXED_TS = "2026-11-20T12:00:00+00:00"


@pytest.fixture
def engine(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    model, metrics, _ = train_pipeline(n_train=800, n_test=200, seed=42)
    version = registry.register("credit-decision", model, metrics)
    registry.promote(version)
    return DecisioningEngine(registry), registry, version


def _member(**overrides):
    member = {
        "member_id": "member-0001",
        "features": {"income": 60000, "debt_ratio": 0.3,
                     "credit_history_years": 8, "delinquencies": 0,
                     "amount": 5000},
        "has_care_gap": True,
        "completed_actions": [],
        "wellness_enrolled": False,
        "last_screening_days_ago": 300,
        "contacts_this_week": 0,
    }
    member.update(overrides)
    return member


def test_decide_picks_highest_scored_eligible_action(engine):
    eng, _, version = engine
    decision = eng.decide(_member(), timestamp=FIXED_TS)
    assert decision["model_version"] == version
    assert decision["chosen_action"] in {a["id"] for a in ACTIONS}
    assert decision["timestamp"] == FIXED_TS
    assert set(decision["scores"]) == {a["id"] for a in ACTIONS}
    assert all(0.0 <= s <= 1.0 for s in decision["scores"].values())
    # The choice must be the highest-scored action that no rule suppressed.
    eligible = [a for a in ACTIONS if not decision["rules_applied"][a["id"]]]
    best = max(eligible, key=lambda a: decision["scores"][a["id"]])["id"]
    assert decision["chosen_action"] == best
    assert decision["rules_applied"]["care_gap_reminder"] == []


def test_open_care_gap_with_high_risk_features_wins(engine):
    eng, _, _ = engine
    # Open gap + high debt ratio and delinquencies: care-gap affinity is
    # at its highest, screening is up to date, wellness already enrolled.
    member = _member(debt_ratio=0.8, delinquencies=3, last_screening_days_ago=30,
                     wellness_enrolled=True)
    decision = eng.decide(member, timestamp=FIXED_TS)
    assert decision["chosen_action"] == "care_gap_reminder"


def test_completed_action_is_suppressed(engine):
    eng, _, _ = engine
    decision = eng.decide(_member(completed_actions=["care_gap_reminder"]),
                          timestamp=FIXED_TS)
    assert "already_completed" in decision["rules_applied"]["care_gap_reminder"]
    assert decision["chosen_action"] != "care_gap_reminder"


def test_no_care_gap_suppresses_reminder(engine):
    eng, _, _ = engine
    decision = eng.decide(_member(has_care_gap=False), timestamp=FIXED_TS)
    assert "no_open_care_gap" in decision["rules_applied"]["care_gap_reminder"]
    assert decision["chosen_action"] != "care_gap_reminder"


def test_fresh_screening_suppresses_screening_nudge(engine):
    eng, _, _ = engine
    decision = eng.decide(_member(last_screening_days_ago=30), timestamp=FIXED_TS)
    assert "screening_up_to_date" in decision["rules_applied"]["preventive_screening_nudge"]


def test_enrolled_member_not_invited_to_wellness(engine):
    eng, _, _ = engine
    decision = eng.decide(_member(wellness_enrolled=True), timestamp=FIXED_TS)
    assert "already_enrolled" in decision["rules_applied"]["wellness_program_invite"]


def test_weekly_contact_cap_suppresses_everything(engine):
    eng, _, _ = engine
    decision = eng.decide(_member(contacts_this_week=2), timestamp=FIXED_TS)
    assert decision["chosen_action"] is None
    assert decision["reason"] == "no eligible action"
    assert all("weekly_contact_cap" in r for r in decision["rules_applied"].values())


def test_decide_with_no_production_model_raises(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    eng = DecisioningEngine(registry)
    with pytest.raises(ValueError):
        eng.decide(_member(), timestamp=FIXED_TS)


def test_decision_log_round_trip(engine, tmp_path):
    eng, _, _ = engine
    path = str(tmp_path / "decisions.jsonl")
    assert read_decisions(path) == []  # missing file reads as empty
    d1 = eng.decide(_member(), timestamp=FIXED_TS)
    d2 = eng.decide(_member(member_id="member-0002"), timestamp=FIXED_TS)
    log_decision(path, d1)
    log_decision(path, d2)
    logged = read_decisions(path)
    assert len(logged) == 2
    assert logged[0]["member_id"] == "member-0001"
    assert logged[1]["member_id"] == "member-0002"
    assert logged[0]["chosen_action"] == d1["chosen_action"]


def test_outcome_report_per_action_and_baseline_comparison():
    # Hand-built decisions so the report math is checked deterministically.
    decisions = [
        {"member_id": "m1", "chosen_action": "care_gap_reminder",
         "baseline_action": "care_gap_reminder"},
        {"member_id": "m2", "chosen_action": "care_gap_reminder",
         "baseline_action": "preventive_screening_nudge"},
        {"member_id": "m3", "chosen_action": "wellness_program_invite",
         "baseline_action": "wellness_program_invite"},
        {"member_id": "m4", "chosen_action": None, "baseline_action": None},
    ]
    outcomes = [
        {"member_id": "m1", "action": "care_gap_reminder", "accepted": True},
        {"member_id": "m2", "action": "care_gap_reminder", "accepted": True},
        {"member_id": "m2", "action": "preventive_screening_nudge", "accepted": False},
        {"member_id": "m3", "action": "wellness_program_invite", "accepted": False},
    ]
    report = outcome_report(decisions, outcomes)
    assert report["per_action"]["care_gap_reminder"] == {
        "decisions": 2, "accepted": 2, "acceptance_rate": 1.0}
    assert report["per_action"]["wellness_program_invite"]["acceptance_rate"] == 0.0
    assert report["model_chosen"] == {"decisions": 3, "accepted": 2,
                                      "acceptance_rate": 0.6667}
    assert report["rule_only_baseline"] == {"decisions": 3, "accepted": 1,
                                            "acceptance_rate": 0.3333}
    assert report["lift_vs_baseline"] == 0.3334


def test_decide_with_baseline_records_baseline_action(engine):
    eng, _, _ = engine
    decision = eng.decide_with_baseline(_member(), timestamp=FIXED_TS)
    assert decision["baseline_action"] == "care_gap_reminder"
    assert decision["chosen_action"] in {a["id"] for a in ACTIONS}


def test_outcome_report_ignores_decisions_without_outcomes(engine):
    eng, _, _ = engine
    decisions = [eng.decide_with_baseline(_member(), timestamp=FIXED_TS)]
    report = outcome_report(decisions, [])
    assert report["model_chosen"]["decisions"] == 0
    assert report["model_chosen"]["acceptance_rate"] is None
    assert report["lift_vs_baseline"] is None


def test_baseline_ignores_model_scores(engine):
    # Member with an open care gap: baseline picks the top-priority
    # eligible action regardless of scores.
    member = _member()
    assert baseline_action(member) == "care_gap_reminder"
    member_capped = _member(contacts_this_week=5)
    assert baseline_action(member_capped) is None


def test_generate_members_is_seeded_and_reproducible():
    first = generate_members(10, seed=7)
    second = generate_members(10, seed=7)
    assert first == second
    assert len(first) == 10
    assert all(m["member_id"].startswith("member-") for m in first)
    assert generate_members(10, seed=8) != first
