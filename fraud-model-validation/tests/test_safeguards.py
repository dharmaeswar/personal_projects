"""Tests for the safeguards analytics module."""

import numpy as np
import pandas as pd
import pytest

from fraud_validation.safeguards import (
    build_audit_trail,
    build_safeguards_section,
    drift_monitor,
    false_positive_review,
    generate_harm_events,
    overturn_rate,
    precision_recall_at_thresholds,
)


@pytest.fixture(scope="module")
def events():
    return generate_harm_events()


def test_events_generation_deterministic():
    pd.testing.assert_frame_equal(generate_harm_events(), generate_harm_events())


def test_events_shape_and_columns(events):
    assert len(events) == 5000
    expected = {"event_id", "category", "week", "model_score", "is_harmful"}
    assert set(events.columns) == expected
    assert events["model_score"].between(0.0, 1.0).all()
    assert set(events["is_harmful"].unique()) <= {0, 1}


def test_harmful_events_score_higher(events):
    harmful = events[events["is_harmful"] == 1]["model_score"]
    benign = events[events["is_harmful"] == 0]["model_score"]
    assert harmful.mean() > benign.mean() + 0.2


def test_precision_recall_table_shape(events):
    table = precision_recall_at_thresholds(
        events["is_harmful"].to_numpy(), events["model_score"].to_numpy()
    )
    assert list(table.columns) == [
        "threshold", "flagged", "true_positives", "false_positives",
        "precision", "recall", "f1",
    ]
    assert list(table["threshold"]) == [0.3, 0.5, 0.7, 0.9]
    assert (table["precision"] >= 0).all() and (table["precision"] <= 1).all()
    assert (table["recall"] >= 0).all() and (table["recall"] <= 1).all()


def test_precision_rises_and_recall_falls_with_threshold(events):
    table = precision_recall_at_thresholds(
        events["is_harmful"].to_numpy(), events["model_score"].to_numpy()
    )
    assert table["precision"].is_monotonic_increasing
    assert table["recall"].is_monotonic_decreasing
    assert table["flagged"].is_monotonic_decreasing


def test_model_beats_base_rate_precision(events):
    table = precision_recall_at_thresholds(
        events["is_harmful"].to_numpy(), events["model_score"].to_numpy()
    )
    base_rate = events["is_harmful"].mean()
    row = table[table["threshold"] == 0.5].iloc[0]
    assert row["precision"] > base_rate
    assert row["recall"] > 0.5


def test_false_positive_review_burden(events):
    review = false_positive_review(events, threshold=0.5)
    assert review["flagged"] == review["false_positives"] + review["true_positives"]
    assert 0.0 < review["fp_share_of_queue"] < 1.0
    assert review["review_hours_wasted_on_fp"] <= review["review_hours_total"]
    assert review["review_hours_total"] > 0
    # A higher threshold flags less, so the review queue shrinks.
    strict = false_positive_review(events, threshold=0.9)
    assert strict["flagged"] < review["flagged"]


def test_drift_monitor_stable_for_same_distribution(events):
    scores = events["model_score"].to_numpy()
    ref = scores[:2500]
    cur = scores[2500:]
    result = drift_monitor(ref, cur)
    assert result["psi"] < 0.1
    assert result["stable"] is True


def test_drift_monitor_detects_shift(events):
    ref = events["model_score"].to_numpy()
    cur = np.clip(ref + 0.4, 0.0, 1.0)
    result = drift_monitor(ref, cur)
    assert result["psi"] > 0.25
    assert result["stable"] is False


def test_audit_trail_shape_and_overturn(events):
    audit = build_audit_trail(events)
    assert len(audit) == len(events)
    expected = {
        "event_id", "category", "week", "model_score", "is_harmful",
        "threshold", "model_decision", "reviewer_decision", "overturned",
    }
    assert set(audit.columns) == expected
    assert set(audit["model_decision"].unique()) <= {"flag", "pass"}
    assert set(audit["reviewer_decision"].unique()) <= {"uphold", "overturn", "pass", "escalate"}
    rates = overturn_rate(audit)
    assert 0.0 < rates["overall_overturn_rate"] < 0.3
    assert 0.0 < rates["flag_overturn_rate"] < 0.5
    assert rates["n_flagged"] == int((audit["model_decision"] == "flag").sum())


def test_audit_trail_deterministic(events):
    a = build_audit_trail(events)
    b = build_audit_trail(events)
    pd.testing.assert_frame_equal(a, b)


def test_report_section_contains_key_content(events):
    section = build_safeguards_section(events)
    for text in [
        "SAFEGUARDS ANALYTICS",
        "Precision / recall by operating threshold",
        "False-positive review",
        "Score drift",
        "Decision audit trail",
    ]:
        assert text in section
