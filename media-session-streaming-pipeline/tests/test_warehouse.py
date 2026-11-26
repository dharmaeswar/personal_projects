from datetime import datetime, timezone

import pandas as pd
import pytest

from session_stream.events import generate_sessions
from session_stream.streaming import sessionize, to_frame
from session_stream.warehouse import (
    build_session_fact, build_title_dimension, update_title_dimension,
    write_bronze, write_gold_sessions, write_silver,
)


def _events_df():
    return to_frame(generate_sessions(5, seed=42))


def test_write_bronze_partitions_by_date(tmp_path):
    files = write_bronze(_events_df(), tmp_path)
    assert files
    assert all("bronze" in str(f) and "event_date=" in str(f) for f in files)
    read = pd.read_parquet(files[0])
    assert len(read) > 0


def test_write_silver_partitions_by_date_and_title(tmp_path):
    files = write_silver(_events_df(), tmp_path)
    assert files
    assert all("silver" in str(f) and "title_id=" in str(f) for f in files)


def test_write_gold_sessions(tmp_path):
    sessions = sessionize(_events_df())
    files = write_gold_sessions(sessions, tmp_path)
    assert files
    read = pd.read_parquet(files[0])
    assert "session_id" in read.columns and "duration_seconds" in read.columns


def test_write_gold_empty_returns_no_files(tmp_path):
    assert write_gold_sessions(pd.DataFrame(), tmp_path) == []


def test_title_dimension_scd2_columns():
    dim = build_title_dimension([
        {"title_id": "title-001", "title_name": "Drama One", "genre": "drama"}])
    assert bool(dim.iloc[0]["is_current"]) is True
    assert pd.isna(dim.iloc[0]["valid_to"])
    assert dim.iloc[0]["title_key"] == "title-001"


def test_update_title_dimension_closes_old_row():
    dim = build_title_dimension([
        {"title_id": "title-001", "title_name": "Drama One", "genre": "drama"}])
    updated = update_title_dimension(
        dim, "title-001", "Drama One: Remastered",
        effective=datetime(2026, 11, 26, tzinfo=timezone.utc))
    assert len(updated) == 2
    current = updated[updated["is_current"]]
    assert len(current) == 1
    assert current.iloc[0]["title_name"] == "Drama One: Remastered"
    old = updated[~updated["is_current"]]
    assert pd.notna(old.iloc[0]["valid_to"])


def test_update_title_dimension_unknown_title_raises():
    dim = build_title_dimension([
        {"title_id": "title-001", "title_name": "Drama One", "genre": "drama"}])
    with pytest.raises(ValueError):
        update_title_dimension(dim, "title-999", "Missing")


def test_build_session_fact_joins_dimension():
    sessions = sessionize(_events_df())
    titles = [{"title_id": t, "title_name": t, "genre": "drama"}
              for t in sessions["title_id"].unique()]
    fact = build_session_fact(sessions, build_title_dimension(titles))
    assert len(fact) == len(sessions)
    assert fact["title_key"].notna().all()
    assert fact["date_key"].str.match(r"^\d{8}$").all()
