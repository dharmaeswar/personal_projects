"""Tests for the home-health episode data-quality module."""

import pandas as pd
import pytest

from lakehouse.home_health import (
    build_episode_summary,
    check_episode_dates,
    check_visit_window,
    generate_episodes,
    generate_home_health,
    generate_visits,
    quarantine_visits,
    validate_episodes,
    validate_visits,
)


def test_generate_episodes_shape():
    episodes = generate_episodes()
    assert len(episodes) == 40
    assert episodes["episode_id"].is_unique
    assert set(episodes.columns) == {
        "episode_id",
        "patient_key",
        "start_date",
        "end_date",
        "discharge_status",
        "diagnosis_group",
    }


def test_generate_visits_inside_episode_window():
    episodes = generate_episodes()
    visits = generate_visits(episodes)
    assert len(visits) >= 120  # 3-7 visits per episode
    merged = visits.merge(
        episodes[["episode_id", "start_date", "end_date"]],
        on="episode_id",
        how="left",
    )
    assert ((merged["visit_date"] >= merged["start_date"]) &
            (merged["visit_date"] <= merged["end_date"])).all()


def test_fixture_plants_nine_bad_rows():
    data = generate_home_health()
    episodes, visits = data["episodes"], data["visits"]
    assert len(episodes) == 40
    # 2 duplicate visit ids + the base visit count
    assert visits["visit_id"].duplicated().sum() == 2
    assert int(visits["episode_id"].isna().sum()) == 2
    assert int((visits["duration_minutes"] < 0).sum()) == 1
    assert int((visits["duration_minutes"] > 480).sum()) == 1
    assert int((visits["episode_id"] == "EP-9999").sum()) == 1
    assert int((episodes["end_date"] < episodes["start_date"]).sum()) == 1


def test_episode_checks_catch_bad_episode():
    data = generate_home_health()
    results = {r.name: r for r in validate_episodes(data["episodes"])}
    assert results["episode_dates"].passed is False
    assert len(results["episode_dates"].failing_rows) == 1
    assert results["completeness"].passed is True
    assert results["uniqueness:episode_id"].passed is True


def test_visit_checks_catch_every_violation_type():
    data = generate_home_health()
    results = {r.name: r for r in validate_visits(data["visits"], data["episodes"])}
    assert results["completeness"].passed is False
    assert results["uniqueness:visit_id"].passed is False
    assert results["range:duration_minutes"].passed is False
    assert len(results["range:duration_minutes"].failing_rows) == 2
    assert results["fk:episode_id->episode_id"].passed is False
    assert results["visit_window"].passed is False
    assert len(results["visit_window"].failing_rows) == 1


def test_visit_window_ignores_null_and_unknown_episodes():
    episodes = pd.DataFrame(
        {
            "episode_id": ["EP-1"],
            "start_date": [pd.Timestamp("2026-01-01")],
            "end_date": [pd.Timestamp("2026-01-31")],
        }
    )
    visits = pd.DataFrame(
        {
            "visit_id": ["V-1", "V-2", "V-3"],
            "episode_id": ["EP-1", None, "EP-404"],
            "visit_date": [
                pd.Timestamp("2026-02-15"),
                pd.Timestamp("2026-01-10"),
                pd.Timestamp("2026-01-10"),
            ],
        }
    )
    result = check_visit_window(visits, episodes)
    assert result.passed is False
    assert result.failing_rows == [0]


def test_episode_dates_pass_on_clean_data():
    episodes = generate_episodes()
    assert check_episode_dates(episodes).passed is True


def test_quarantine_keeps_every_bad_visit_with_reason():
    data = generate_home_health()
    silver, quarantine = quarantine_visits(data["visits"], data["episodes"])
    # 8 bad visit rows: 2 dup ids, 2 null episode, 1 out-of-window,
    # 1 negative duration, 1 unknown episode, 1 over-cap duration
    assert len(quarantine) == 8
    assert len(silver) + len(quarantine) == len(data["visits"])
    assert quarantine["quarantine_reason"].str.len().gt(0).all()
    assert silver["visit_id"].is_unique
    assert silver["episode_id"].notna().all()
    assert ((silver["duration_minutes"] >= 0) &
            (silver["duration_minutes"] <= 480)).all()


def test_episode_summary_reconciles_to_silver():
    data = generate_home_health()
    silver, _ = quarantine_visits(data["visits"], data["episodes"])
    summary = build_episode_summary(silver, data["episodes"])
    assert summary["visit_count"].sum() == len(silver)
    assert summary["total_minutes"].sum() == silver["duration_minutes"].sum()
    assert set(summary.columns) == {
        "episode_id",
        "visit_count",
        "total_minutes",
        "avg_minutes",
        "discharge_status",
        "diagnosis_group",
    }


def test_episode_summary_avg_minutes_matches():
    data = generate_home_health()
    silver, _ = quarantine_visits(data["visits"], data["episodes"])
    summary = build_episode_summary(silver, data["episodes"])
    first = summary.iloc[0]
    ep_visits = silver[silver["episode_id"] == first["episode_id"]]
    assert first["visit_count"] == len(ep_visits)
    assert first["total_minutes"] == ep_visits["duration_minutes"].sum()
    assert first["avg_minutes"] == pytest.approx(
        ep_visits["duration_minutes"].mean(), abs=0.05
    )


def test_generation_is_deterministic():
    a = generate_home_health()
    b = generate_home_health()
    pd.testing.assert_frame_equal(a["episodes"], b["episodes"])
    pd.testing.assert_frame_equal(a["visits"], b["visits"])


def test_clean_data_passes_all_visit_checks():
    episodes = generate_episodes()
    visits = generate_visits(episodes)
    assert all(r.passed for r in validate_visits(visits, episodes))
    assert all(r.passed for r in validate_episodes(episodes))
