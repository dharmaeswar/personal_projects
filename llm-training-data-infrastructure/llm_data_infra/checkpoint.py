"""Checkpointing for fault-tolerant training-data loads.

A load run writes a small JSON checkpoint after every shard commits,
recording which shards are done. If the process dies mid-run, the next
run reads the checkpoint and loads only the shards that are not done —
no shard is loaded twice, and the store's content-hash dedup makes even
an interrupted shard safe to re-run (already-inserted records count as
duplicates, never as new rows).

Checkpoint file shape:
  {"run_id": str, "dataset": str, "version": str, "num_shards": int,
   "done_shards": [int, ...], "updated_at": str}
"""
import json
import os
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_checkpoint(run_id: str, dataset: str, version: str, num_shards: int) -> dict:
    return {"run_id": run_id, "dataset": dataset, "version": version,
            "num_shards": num_shards, "done_shards": [], "updated_at": _now_iso()}


def load_checkpoint(path: str) -> dict | None:
    """Read a checkpoint file; returns None when the file is absent."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    if not isinstance(state, dict) or "done_shards" not in state:
        raise ValueError(f"checkpoint file {path} is not a valid checkpoint")
    return state


def save_checkpoint(path: str, state: dict) -> None:
    """Atomically write a checkpoint (temp file + rename)."""
    state = dict(state)
    state["updated_at"] = _now_iso()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def mark_shard_done(state: dict, shard: int) -> dict:
    if shard not in state["done_shards"]:
        state["done_shards"] = sorted(state["done_shards"] + [shard])
    return state


def pending_shards(state: dict) -> list[int]:
    """Shard indexes not yet checkpointed as done, in order."""
    done = set(state["done_shards"])
    return [i for i in range(state["num_shards"]) if i not in done]


def is_complete(state: dict) -> bool:
    return pending_shards(state) == []
