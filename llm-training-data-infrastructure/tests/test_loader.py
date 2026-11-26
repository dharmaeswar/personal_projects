"""Tests for the parallel sharded loader and checkpoint/resume."""
import os

import pytest

from llm_data_infra import checkpoint, loader
from llm_data_infra.store import Store


@pytest.fixture()
def store():
    s = Store(":memory:")
    yield s
    s.close()


def _dataset(store, name="webtext-train-v1"):
    ds = store.create_dataset(name, "text", "data-platform", "demo corpus")
    store.create_version(ds, "1.0")
    return ds


def _corpus():
    clean = [
        {"text": f"Gradient descent updates model weights each batch, example {i}."}
        for i in range(20)
    ]
    clean.append({"text": "Short"})  # quarantined by gates
    clean.append({"text": "Contact help@example.com for details on the program."})
    return clean


def test_sharding_is_deterministic():
    records = _corpus()
    first = loader.shard_records(records, 4)
    second = loader.shard_records(records, 4)
    assert first == second
    assert sum(len(s) for s in first) == len(records)
    # Same record always lands in the same shard.
    assert loader.shard_index(records[0], 4) == loader.shard_index(records[0], 4)
    with pytest.raises(ValueError):
        loader.shard_records(records, 0)


def test_parallel_load_matches_serial_totals(store):
    ds = _dataset(store)
    corpus = _corpus() + _corpus()[:5]  # 5 planted duplicates
    result = loader.load_parallel(store, ds, "1.0", corpus, "text",
                                  num_shards=4, num_workers=4)
    totals = result["totals"]
    assert totals["received"] == len(corpus)
    assert totals["accepted"] + totals["duplicates"] + totals["quarantined"] \
        == totals["received"]
    assert totals["duplicates"] == 5
    assert totals["quarantined"] == 2
    assert len(result["shards"]) == 4
    stored = store.list_records(ds, "1.0", status="accepted")
    assert len(stored) == totals["accepted"]
    assert len({r["content_hash"] for r in stored}) == len(stored)


def test_parallel_load_is_idempotent(store):
    ds = _dataset(store)
    corpus = _corpus()
    first = loader.load_parallel(store, ds, "1.0", corpus, "text")
    second = loader.load_parallel(store, ds, "1.0", corpus, "text")
    assert first["totals"]["accepted"] == second["totals"]["duplicates"]
    assert second["totals"]["accepted"] == 0
    stored = store.list_records(ds, "1.0", status="accepted")
    assert len(stored) == first["totals"]["accepted"]


def test_checkpoint_round_trip_and_resume_plan(tmp_path):
    path = str(tmp_path / "ckpt.json")
    assert checkpoint.load_checkpoint(path) is None
    state = checkpoint.new_checkpoint("run-1", "webtext-train-v1", "1.0", 4)
    assert checkpoint.pending_shards(state) == [0, 1, 2, 3]
    assert not checkpoint.is_complete(state)
    checkpoint.mark_shard_done(state, 1)
    checkpoint.mark_shard_done(state, 0)
    checkpoint.save_checkpoint(path, state)
    reloaded = checkpoint.load_checkpoint(path)
    assert reloaded["done_shards"] == [0, 1]
    assert checkpoint.pending_shards(reloaded) == [2, 3]
    checkpoint.mark_shard_done(reloaded, 2)
    checkpoint.mark_shard_done(reloaded, 3)
    assert checkpoint.is_complete(reloaded)
    with pytest.raises(ValueError):
        bad = tmp_path / "bad.json"
        bad.write_text('{"nope": true}')
        checkpoint.load_checkpoint(str(bad))


def test_crash_then_resume_equals_clean_run(store, tmp_path):
    ds = _dataset(store)
    corpus = _corpus() + _corpus()[:5]
    path = str(tmp_path / "ckpt.json")
    state = checkpoint.new_checkpoint("run-1", "webtext-train-v1", "1.0", 4)

    # Crash pass: commit shards 0-1 only, checkpointing each.
    shards = loader.shard_records(corpus, 4)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        evaluated = list(
            pool.map(lambda s: loader.evaluate_shard(s, "text"), shards)
        )
    crash_totals = {"received": 0, "accepted": 0, "duplicates": 0, "quarantined": 0}
    for idx in (0, 1):
        counts = loader.commit_evaluated(store, ds, "1.0", evaluated[idx], "text")
        for key in crash_totals:
            crash_totals[key] += counts[key]
        checkpoint.mark_shard_done(state, idx)
        checkpoint.save_checkpoint(path, state)

    # Resume pass: only pending shards load.
    resumed_state = checkpoint.load_checkpoint(path)
    assert checkpoint.pending_shards(resumed_state) == [2, 3]
    resume_totals = {"received": 0, "accepted": 0, "duplicates": 0, "quarantined": 0}
    for idx in checkpoint.pending_shards(resumed_state):
        counts = loader.commit_evaluated(store, ds, "1.0", evaluated[idx], "text")
        for key in resume_totals:
            resume_totals[key] += counts[key]
        checkpoint.mark_shard_done(resumed_state, idx)
    final = {k: crash_totals[k] + resume_totals[k] for k in crash_totals}

    # Clean single-pass reference.
    ref = Store(":memory:")
    ref_ds = _dataset(ref)
    reference = loader.load_parallel(ref, ref_ds, "1.0", corpus, "text",
                                     num_shards=4, num_workers=4)
    ref.close()
    assert final == reference["totals"]
