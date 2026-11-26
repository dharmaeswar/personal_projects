"""Point-in-time-correct feature and label engineering.

Each training row is one (user, content, impression). The label is derived
only from events that happen *after* the impression and inside the label
horizon; every history feature is computed only from events *before* the
impression. That as-of discipline is what keeps the training set free of
label leakage — the most common way a personalization training pipeline
silently goes wrong.

Spark equivalents: ``rangeBetween`` window functions for the history
features, and a time-bounded self-join for the labels.
"""

from __future__ import annotations

import pandas as pd

LABEL_HORIZON_HOURS = 24
CONTENT_HISTORY_DAYS = 7


def build_training_rows(clean: pd.DataFrame,
                        horizon_hours: int = LABEL_HORIZON_HOURS) -> pd.DataFrame:
    """Build one labelled training row per impression.

    Columns: user/content keys, impression time, label_completed (1 if a
    view_complete for the same user+content lands within the horizon),
    label_liked, user history features, content history features, and
    content/device/surface context.
    """
    df = clean.copy()
    df["event_ts"] = pd.to_datetime(df["event_ts"])
    impressions = df[df["event_type"] == "impression"].copy()
    if impressions.empty:
        return pd.DataFrame(columns=[
            "user_id", "content_id", "impression_ts", "label_completed",
            "label_liked", "user_prior_views", "user_prior_completions",
            "user_avg_watch_ratio", "content_prior_7d_views",
            "content_duration_s", "genre", "title_type", "device", "surface",
        ])
    horizon = pd.Timedelta(hours=horizon_hours)
    history_window = pd.Timedelta(days=CONTENT_HISTORY_DAYS)

    completions = df[df["event_type"] == "view_complete"]
    likes = df[df["event_type"] == "like"]
    starts = df[df["event_type"] == "view_start"]

    rows = []
    for imp in impressions.itertuples(index=False):
        imp_ts = imp.event_ts
        pair = (df["user_id"] == imp.user_id) & (df["content_id"] == imp.content_id)
        after = df[pair & (df["event_ts"] > imp_ts) & (df["event_ts"] <= imp_ts + horizon)]
        label_completed = int((after["event_type"] == "view_complete").any())
        label_liked = int((after["event_type"] == "like").any())

        prior_user = df[(df["user_id"] == imp.user_id) & (df["event_ts"] < imp_ts)]
        prior_starts = prior_user[prior_user["event_type"] == "view_start"]
        prior_completions = prior_user[prior_user["event_type"] == "view_complete"]
        if len(prior_starts):
            ratios = prior_starts["watch_seconds"] / prior_starts["content_duration_s"]
            avg_watch_ratio = round(float(ratios.mean()), 4)
        else:
            avg_watch_ratio = 0.0

        content_window = df[
            (df["content_id"] == imp.content_id)
            & (df["event_type"] == "view_start")
            & (df["event_ts"] < imp_ts)
            & (df["event_ts"] >= imp_ts - history_window)
        ]
        rows.append({
            "user_id": imp.user_id,
            "content_id": imp.content_id,
            "impression_ts": imp_ts,
            "label_completed": label_completed,
            "label_liked": label_liked,
            "user_prior_views": int(len(prior_starts)),
            "user_prior_completions": int(len(prior_completions)),
            "user_avg_watch_ratio": avg_watch_ratio,
            "content_prior_7d_views": int(len(content_window)),
            "content_duration_s": imp.content_duration_s,
            "genre": imp.genre,
            "title_type": imp.title_type,
            "device": imp.device,
            "surface": imp.surface,
        })
    out = pd.DataFrame(rows)
    return out.sort_values("impression_ts").reset_index(drop=True)


def label_rates(rows: pd.DataFrame) -> dict:
    """Completion / like rates of a training set, for a quick sanity check."""
    if rows.empty:
        return {"rows": 0, "completion_rate": 0.0, "like_rate": 0.0}
    return {
        "rows": len(rows),
        "completion_rate": round(float(rows["label_completed"].mean()), 4),
        "like_rate": round(float(rows["label_liked"].mean()), 4),
    }
