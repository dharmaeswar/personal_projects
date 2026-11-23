"""Tests for micro-batch streaming ingest (lakehouse/streaming.py)."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.streaming import (
    StreamCheckpoint,
    generate_event_stream,
    process_micro_batch,
    run_stream,
    split_micro_batches,
)


@pytest.fixture(scope="module")
def stream():
    return generate_event_stream()


def test_stream_shape(stream):
    # 120 base events + 3 duplicate deliveries + 2 late events.
    assert len(stream) == 125
    assert stream["offset"].is_unique
    assert stream["event_id"].duplicated().sum() == 3


def test_split_micro_batches(stream):
    batches = split_micro_batches(stream, batch_size=40)
    assert len(batches) == 4
    assert [len(b) for b in batches] == [40, 40, 40, 5]
    assert batches[0]["offset"].min() == 0
    assert batches[-1]["offset"].max() == 124


def test_run_stream_exactly_once(stream):
    result = run_stream(stream)
    assert len(result["accepted"]) == 120
    assert len(result["late"]) == 2
    assert len(result["duplicates"]) == 3
    assert result["total_arrived"] == 125
    # Exactly once: every accepted event id appears once.
    assert result["accepted"]["event_id"].is_unique
    # Late events are the two planted ones.
    assert set(result["late"]["event_id"]) == {"E90001", "E90002"}
    # Duplicates are re-deliveries of earlier events.
    assert set(result["duplicates"]["event_id"]) == {"E00005", "E00040", "E00090"}
    # Per-batch stats add up.
    assert sum(b["accepted"] for b in result["batches"]) == 120
    assert sum(b["late_dropped"] for b in result["batches"]) == 2
    assert sum(b["duplicates_dropped"] for b in result["batches"]) == 3


def test_watermark_advances(stream):
    result = run_stream(stream)
    checkpoint = result["checkpoint"]
    assert checkpoint.last_offset == 124
    assert checkpoint.watermark is not None
    assert len(checkpoint.processed_event_ids) == 120


def test_reprocessing_a_batch_is_a_noop(stream):
    batches = split_micro_batches(stream, batch_size=40)
    checkpoint = StreamCheckpoint()
    accepted, _, _, checkpoint = process_micro_batch(batches[0], checkpoint)
    assert len(accepted) == 40
    accepted2, late2, dup2, _ = process_micro_batch(batches[0], checkpoint)
    assert len(accepted2) == 0
    assert len(late2) == 0
    assert len(dup2) == 0


def test_checkpoint_round_trip(stream):
    result = run_stream(stream)
    restored = StreamCheckpoint.from_dict(result["checkpoint"].to_dict())
    assert restored.last_offset == result["checkpoint"].last_offset
    assert restored.watermark == result["checkpoint"].watermark
    assert restored.processed_event_ids == result["checkpoint"].processed_event_ids


def test_late_event_dropped_not_merged(stream):
    result = run_stream(stream)
    assert "E90001" not in set(result["accepted"]["event_id"])
    assert "E90002" not in set(result["accepted"]["event_id"])
