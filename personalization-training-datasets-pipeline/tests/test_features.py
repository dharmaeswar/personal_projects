import pandas as pd

from personalization_data import features


def _events():
    rows = [
        # User U1 watches C1 fully after the impression -> label 1.
        ("E1", "U1", "C1", "impression", "2026-11-02 10:00", "mobile", "news", "movie", 600, None),
        ("E2", "U1", "C1", "view_start", "2026-11-02 10:01", "mobile", "news", "movie", 600, 600.0),
        ("E3", "U1", "C1", "view_complete", "2026-11-02 10:11", "mobile", "news", "movie", 600, 600.0),
        # User U2 only gets an impression, no follow-on -> label 0.
        ("E4", "U2", "C2", "impression", "2026-11-02 11:00", "web", "drama", "series", 1500, None),
        # User U1's earlier history: one prior view of C2 (before the C1 impression).
        ("E5", "U1", "C2", "view_start", "2026-11-01 09:00", "mobile", "drama", "series", 1500, 750.0),
        # A completion AFTER the 24h horizon must not label the impression.
        ("E6", "U2", "C2", "view_complete", "2026-11-04 12:00", "web", "drama", "series", 1500, 1500.0),
    ]
    df = pd.DataFrame(rows, columns=[
        "event_id", "user_id", "content_id", "event_type", "event_ts",
        "device", "genre", "title_type", "content_duration_s", "watch_seconds"])
    df["event_ts"] = pd.to_datetime(df["event_ts"])
    df["ingested_at"] = df["event_ts"] + pd.Timedelta(minutes=1)
    df["surface"] = "mobile"
    df["country"] = "US"
    return df


def test_labels_use_only_events_inside_horizon():
    rows = features.build_training_rows(_events())
    assert len(rows) == 2
    u1 = rows[rows["user_id"] == "U1"].iloc[0]
    u2 = rows[rows["user_id"] == "U2"].iloc[0]
    assert u1["label_completed"] == 1
    assert u2["label_completed"] == 0  # completion was 49h later, past the horizon


def test_history_features_use_only_prior_events():
    rows = features.build_training_rows(_events())
    u1 = rows[rows["user_id"] == "U1"].iloc[0]
    assert u1["user_prior_views"] == 1
    assert u1["user_prior_completions"] == 0
    assert u1["user_avg_watch_ratio"] == 0.5  # 750 / 1500
    u2 = rows[rows["user_id"] == "U2"].iloc[0]
    assert u2["user_prior_views"] == 0
    assert u2["user_avg_watch_ratio"] == 0.0


def test_content_history_window():
    rows = features.build_training_rows(_events())
    u1 = rows[rows["user_id"] == "U1"].iloc[0]
    # The prior C2 view is a different content, so C1's 7-day view count is 0.
    assert u1["content_prior_7d_views"] == 0


def test_empty_input_returns_empty_frame():
    empty = pd.DataFrame(columns=["event_id", "user_id", "content_id", "event_type",
                                  "event_ts", "device", "genre", "title_type",
                                  "content_duration_s", "watch_seconds"])
    assert features.build_training_rows(empty).empty
    assert features.label_rates(pd.DataFrame()) == {"rows": 0, "completion_rate": 0.0, "like_rate": 0.0}


def test_generated_data_label_rates_are_sane():
    from personalization_data import events, quality
    raw = events.generate_events(n_impressions=200, seed=42)
    clean, _ = quality.cleanse(raw)
    rows = features.build_training_rows(clean)
    rates = features.label_rates(rows)
    assert rates["rows"] == 200
    assert 0.2 < rates["completion_rate"] < 0.8
