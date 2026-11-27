from signals.batch import build_batch_signals, build_user_context, recency_weight
from signals.ingest import ingest_batch
from signals.models import Consent
from tests.conftest import NOW, raw_event


def _events():
    raw = [
        raw_event("e1", payload={"workflow": "draft-email", "feature": "draft",
                                 "goal": "writing", "duration_seconds": 60}),
        raw_event("e2", payload={"workflow": "draft-email", "feature": "draft",
                                 "goal": "writing", "duration_seconds": 90}),
        raw_event("e3", payload={"workflow": "plan-day", "feature": "schedule",
                                 "goal": "productivity", "duration_seconds": 30}),
        raw_event("e4", event_type="experimentation",
                  payload={"experiment": "exp-a", "experiment_arm": "treatment"}),
        raw_event("e5", event_type="telemetry",
                  payload={"workflow": "draft-email", "feature": "draft",
                           "goal": "writing", "duration_seconds": 10}),
    ]
    accepted, _ = ingest_batch(raw, set(), now=NOW)
    return accepted


def test_top_workflow_is_most_frequent(consent):
    profile = build_user_context("user-01", _events(), consent, "r1", NOW)
    assert profile.top_workflows[0] == "draft-email"
    assert profile.preferred_features[0] == "draft"


def test_goal_affinity_sums_to_one(consent):
    profile = build_user_context("user-01", _events(), consent, "r1", NOW)
    assert abs(sum(profile.goal_affinity.values()) - 1.0) < 0.01
    assert profile.goal_affinity["writing"] > profile.goal_affinity["productivity"]


def test_experiment_arm_recorded(consent):
    profile = build_user_context("user-01", _events(), consent, "r1", NOW)
    assert profile.experiment_arms == {"exp-a": "treatment"}


def test_telemetry_count_recorded(consent):
    profile = build_user_context("user-01", _events(), consent, "r1", NOW)
    assert profile.telemetry_event_count == 1


def test_opted_out_telemetry_excluded_from_profile():
    consent = Consent(user_id="user-01", telemetry=False)
    profile = build_user_context("user-01", _events(), consent, "r1", NOW)
    assert profile.telemetry_event_count == 0


def test_recency_weight_decays():
    from datetime import timedelta
    recent = recency_weight(NOW - timedelta(days=1), NOW)
    old = recency_weight(NOW - timedelta(days=14), NOW)
    assert recent > old and 0 < old < 1


def test_batch_signals_cover_workflow_feature_goal_arm(consent):
    profile = build_user_context("user-01", _events(), consent, "r1", NOW)
    signals = build_batch_signals(profile, "r1")
    types = {s.signal_type for s in signals}
    assert {"workflow_affinity", "preferred_feature", "goal_affinity",
            "experiment_arm", "telemetry_activity"} <= types
    assert all(0.0 <= s.score <= 1.0 for s in signals)
    assert all(s.source_event_ids for s in signals)
