import pandas as pd
import pytest

from personalization_data import events, modeling, quality


def _clean():
    raw = events.generate_events(n_impressions=60, seed=42)
    clean, _ = quality.cleanse(raw)
    return clean


def test_dim_user_one_row_per_user():
    clean = _clean()
    dim = modeling.build_dim_user(clean)
    assert dim["user_id"].is_unique
    assert set(dim.columns) >= {"user_id", "first_seen_ts", "country", "primary_device"}


def test_dim_content_scd2_change():
    clean = _clean()
    dim = modeling.build_dim_content(clean)
    assert dim["is_current"].all()
    content = dim.iloc[0]["content_id"]
    updated = modeling.apply_content_change(
        dim, content, "2026-11-10", genre="sports")
    rows = updated[updated["content_id"] == content]
    assert len(rows) == 2
    assert rows["is_current"].sum() == 1
    assert rows[rows["is_current"]].iloc[0]["genre"] == "sports"
    assert rows[~rows["is_current"]].iloc[0]["valid_to"] == pd.Timestamp("2026-11-10")
    with pytest.raises(ValueError):
        modeling.apply_content_change(dim, "C9999", "2026-11-10", genre="news")


def test_dim_date_and_fact_cover_all_events():
    clean = _clean()
    dim_user = modeling.build_dim_user(clean)
    dim_content = modeling.build_dim_content(clean)
    dim_date = modeling.build_dim_date(clean)
    fact = modeling.build_fact_interactions(clean, dim_user, dim_content)
    assert len(fact) == len(clean)
    assert fact["event_id"].is_unique
    assert set(dim_date["date"]) == set(pd.to_datetime(clean["event_ts"]).dt.normalize())
