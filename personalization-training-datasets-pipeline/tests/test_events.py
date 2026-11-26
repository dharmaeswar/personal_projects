import pandas as pd

from personalization_data import events


def test_generate_is_seeded_and_reproducible():
    a = events.generate_events(n_impressions=50, seed=42)
    b = events.generate_events(n_impressions=50, seed=42)
    assert a.equals(b)
    assert len(a) > 50  # impressions plus follow-on events plus ~2% redeliveries


def test_event_types_and_columns():
    df = events.generate_events(n_impressions=20, seed=7)
    assert set(df["event_type"].unique()) <= set(events.EVENT_TYPES)
    assert list(df.columns) == events.COLUMNS
    assert (df["event_type"] == "impression").sum() == 20


def test_redelivered_events_share_event_id():
    df = events.generate_events(n_impressions=200, seed=42)
    dupes = df[df.duplicated("event_id", keep=False)]
    assert len(dupes) > 0
    # Same event_id, later ingested_at on the redelivery.
    for _, group in dupes.groupby("event_id"):
        assert group["ingested_at"].nunique() == 2


def test_watch_never_exceeds_duration_in_clean_generation():
    df = events.generate_events(n_impressions=100, seed=3)
    valid = df.dropna(subset=["watch_seconds"])
    assert (valid["watch_seconds"] <= valid["content_duration_s"]).all()
    assert (valid["watch_seconds"] >= 0).all()
