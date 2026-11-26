"""Parallel sharded loading for large-scale model training data.

Covers two of the HAIL training-infra problems: training data loading
at scale and parallelism.

Design, stated honestly:
- Records are assigned to shards deterministically by content hash, so
  the same record always lands in the same shard and a re-run never
  moves work between shards.
- Quality-gate evaluation (the CPU work) runs in parallel across shards
  on a worker pool. The SQLite commit phase is single-threaded on
  purpose: one writer avoids database-lock contention, and the dedup
  check in the store makes a re-ingest idempotent.
- Every shard reports its own counts; the loader aggregates them, so a
  slow or dirty shard is visible instead of hidden in a total.
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from . import quality
from .store import Store


def shard_index(payload: dict, num_shards: int) -> int:
    """Deterministic shard for a record, from its content hash."""
    if num_shards < 1:
        raise ValueError("num_shards must be >= 1")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return int(digest, 16) % num_shards


def shard_records(records: list[dict], num_shards: int) -> list[list[dict]]:
    """Split records into deterministic shards by content hash."""
    shards: list[list[dict]] = [[] for _ in range(num_shards)]
    for payload in records:
        shards[shard_index(payload, num_shards)].append(payload)
    return shards


def evaluate_shard(records: list[dict], modality: str) -> list[tuple[dict, list[str]]]:
    """Run the quality gates over one shard's records.

    Pure function (no store access), so it is safe to run in a worker
    thread. Returns (payload, failures) per record; an empty failures
    list means the record passes.
    """
    return [(payload, quality.run_gates(payload, modality)) for payload in records]


def commit_evaluated(store: Store, dataset_id: int, version: str,
                     evaluated: list[tuple[dict, list[str]]], modality: str) -> dict:
    """Insert gate-evaluated records, reusing the store's dedup and
    quarantine rules. Same counting shape as ingestion.ingest_batch."""
    received = accepted = duplicates = quarantined = 0
    for payload, failures in evaluated:
        received += 1
        if failures:
            rec_id = store.insert_record(dataset_id, version, payload, modality)
            if rec_id is not None:
                store.set_record_status(rec_id, "quarantined")
            store.record_quality_check(
                dataset_id, version, "gates", 0, 1, "; ".join(failures)
            )
            quarantined += 1
            continue
        rec_id = store.insert_record(dataset_id, version, payload, modality)
        if rec_id is None:
            duplicates += 1
            continue
        accepted += 1
    return {"received": received, "accepted": accepted,
            "duplicates": duplicates, "quarantined": quarantined}


def load_parallel(store: Store, dataset_id: int, version: str,
                  records: list[dict], modality: str,
                  num_shards: int = 4, num_workers: int = 4) -> dict:
    """Load records through parallel gate evaluation, then commit.

    Returns per-shard counts plus totals. Records one ingestion job of
    kind "parallel" with the totals. Re-running the same records is
    safe: duplicates are counted, not re-inserted.
    """
    if num_workers < 1:
        raise ValueError("num_workers must be >= 1")
    shards = shard_records(records, num_shards)
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        evaluated_shards = list(
            pool.map(lambda shard: evaluate_shard(shard, modality), shards)
        )
    per_shard = []
    totals = {"received": 0, "accepted": 0, "duplicates": 0, "quarantined": 0}
    for idx, evaluated in enumerate(evaluated_shards):
        counts = commit_evaluated(store, dataset_id, version, evaluated, modality)
        per_shard.append({"shard": idx, **counts})
        for key in totals:
            totals[key] += counts[key]
    store.record_ingestion_job(dataset_id, version, "parallel", **totals)
    store.audit("ingestion_job", dataset_id, "parallel",
                f"v{version}: {totals['accepted']} accepted, "
                f"{totals['duplicates']} dup, {totals['quarantined']} quarantined "
                f"across {num_shards} shards")
    return {"shards": per_shard, "totals": totals}
