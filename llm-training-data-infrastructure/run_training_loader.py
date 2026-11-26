"""Demo: parallel sharded load with crash + resume (fault tolerance).

Seeds a synthetic corpus of 200 text records (with planted duplicates
and dirty records), then loads it in 4 shards:

1. First pass: evaluates all shards in parallel, commits shards 0-1,
   then simulates a worker crash before shard 2.
2. Second pass: reads the checkpoint, sees shards 0-1 done, commits
   only shards 2-3, and finishes the run.

The final totals must equal a clean single-pass load, and no record is
inserted twice (the store's content-hash dedup guarantees it).

Usage: python run_training_loader.py
Writes: training_loader_report.json
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

from llm_data_infra import checkpoint, loader
from llm_data_infra.store import Store

DB_PATH = "training_loader.db"
CHECKPOINT_PATH = "training_loader_checkpoint.json"
REPORT_PATH = "training_loader_report.json"
NUM_SHARDS = 4
NUM_WORKERS = 4


def build_corpus(n: int = 200) -> list[dict]:
    """Synthetic text corpus: clean records, planted duplicates, and
    dirty records (too short / PII) that the quality gates quarantine."""
    topics = [
        "Gradient descent updates model weights by stepping against the loss gradient each batch.",
        "Attention layers let each token weigh every other token in the sequence.",
        "Data parallelism splits each batch across devices and averages the gradients.",
        "Checkpointing saves model and optimizer state so a crashed run can resume.",
        "Mixed precision training keeps master weights in float32 and computes in float16.",
        "Pipeline parallelism assigns different model layers to different devices.",
        "Tokenizers convert raw text into integer ids the model can embed.",
        "Learning rate schedules warm up then decay to stabilise large training runs.",
    ]
    records = []
    for i in range(n):
        topic = topics[i % len(topics)]
        records.append({"text": f"{topic} (example {i})", "source": "synthetic"})
    # Planted duplicates: 10 records repeated verbatim.
    records.extend(records[:10])
    # Planted dirty records: 5 too short, 5 with an email pattern.
    records.extend({"text": "Short", "source": "synthetic"} for _ in range(5))
    records.extend(
        {"text": "Contact the team at help@example.com for details on the program.",
         "source": "synthetic"}
        for _ in range(5)
    )
    return records


def load_shards_with_checkpoint(store: Store, dataset_id: int, version: str,
                                records: list[dict], modality: str,
                                state: dict, crash_after: int | None = None) -> dict:
    """Evaluate all shards in parallel, then commit them one by one,
    checkpointing after each commit. crash_after simulates a worker
    dying after that many shards are committed."""
    shards = loader.shard_records(records, state["num_shards"])
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
        evaluated = list(
            pool.map(lambda s: loader.evaluate_shard(s, modality), shards)
        )
    per_shard = []
    totals = {"received": 0, "accepted": 0, "duplicates": 0, "quarantined": 0}
    committed = 0
    crashed = False
    for idx in checkpoint.pending_shards(state):
        counts = loader.commit_evaluated(
            store, dataset_id, version, evaluated[idx], modality
        )
        per_shard.append({"shard": idx, **counts})
        for key in totals:
            totals[key] += counts[key]
        checkpoint.mark_shard_done(state, idx)
        checkpoint.save_checkpoint(CHECKPOINT_PATH, state)
        committed += 1
        if crash_after is not None and committed >= crash_after:
            crashed = True
            break
    store.record_ingestion_job(dataset_id, version, "parallel-checkpointed", **totals)
    return {"shards": per_shard, "totals": totals, "crashed": crashed}


def main() -> dict:
    for path in (DB_PATH, CHECKPOINT_PATH):
        if os.path.exists(path):
            os.remove(path)
    corpus = build_corpus()
    store = Store(DB_PATH)
    ds = store.create_dataset(
        "webtext-train-v1", "text", "data-platform",
        "Synthetic pretraining corpus for the parallel-loader demo.",
    )
    store.create_version(ds, "1.0")

    state = checkpoint.new_checkpoint(
        run_id="demo-run-1", dataset="webtext-train-v1",
        version="1.0", num_shards=NUM_SHARDS,
    )
    first_pass = load_shards_with_checkpoint(store, ds, "1.0", corpus, "text",
                                             state, crash_after=2)
    crashed = first_pass["crashed"]
    if crashed:
        print("crash simulated after 2 shards")
        print("checkpoint after crash:", checkpoint.load_checkpoint(CHECKPOINT_PATH))

    resumed_state = checkpoint.load_checkpoint(CHECKPOINT_PATH)
    resumed = load_shards_with_checkpoint(store, ds, "1.0", corpus, "text",
                                          resumed_state, crash_after=None)

    # Final totals = crash pass + resume pass (each shard committed
    # exactly once). Duplicates are counted, never re-inserted, so the
    # crash + resume total must equal one clean single-pass load.
    final_totals = {
        key: first_pass["totals"][key] + resumed["totals"][key]
        for key in ("received", "accepted", "duplicates", "quarantined")
    }

    # Clean single-pass reference, on a fresh in-memory store.
    ref_store = Store(":memory:")
    ref_ds = ref_store.create_dataset("webtext-train-v1", "text", "data-platform")
    ref_store.create_version(ref_ds, "1.0")
    reference = loader.load_parallel(ref_store, ref_ds, "1.0", corpus, "text",
                                     num_shards=NUM_SHARDS, num_workers=NUM_WORKERS)
    ref_store.close()

    stored = store.list_records(ds, "1.0", status="accepted")
    report = {
        "corpus_records": len(corpus),
        "crash_simulated": crashed,
        "checkpoint_after_crash": checkpoint.load_checkpoint(CHECKPOINT_PATH),
        "resumed_shards": resumed["shards"],
        "final_totals_crash_plus_resume": final_totals,
        "reference_totals_single_pass": reference["totals"],
        "totals_match_reference": final_totals == reference["totals"],
        "accepted_records_stored": len(stored),
        "no_duplicates_stored": len({r["content_hash"] for r in stored}) == len(stored),
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    store.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    main()
