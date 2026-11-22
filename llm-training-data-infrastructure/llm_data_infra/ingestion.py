"""Batch and streaming ingestion with dedup, quality gates and quarantine.

Flow per record: content-hash dedup against the dataset version ->
quality gates -> accepted, or quarantined with the failure reasons
recorded. Every run is logged as an ingestion job with counts.
"""
from . import quality
from .store import Store


def ingest_batch(store: Store, dataset_id: int, version: str,
                 records: list[dict], modality: str) -> dict:
    received = accepted = duplicates = quarantined = 0
    for payload in records:
        received += 1
        failures = quality.run_gates(payload, modality)
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
    store.record_ingestion_job(dataset_id, version, "batch",
                               received, accepted, duplicates, quarantined)
    store.audit("ingestion_job", dataset_id, "batch",
                f"v{version}: {accepted} accepted, {duplicates} dup, {quarantined} quarantined")
    return {"received": received, "accepted": accepted,
            "duplicates": duplicates, "quarantined": quarantined}


def ingest_stream(store: Store, dataset_id: int, version: str,
                  record_iter, modality: str) -> dict:
    """Streaming ingestion: same gates, one record at a time from an
    iterator (models a Kafka-style consumer loop)."""
    received = accepted = duplicates = quarantined = 0
    for payload in record_iter:
        received += 1
        failures = quality.run_gates(payload, modality)
        if failures:
            rec_id = store.insert_record(dataset_id, version, payload, modality)
            if rec_id is not None:
                store.set_record_status(rec_id, "quarantined")
            quarantined += 1
            continue
        rec_id = store.insert_record(dataset_id, version, payload, modality)
        if rec_id is None:
            duplicates += 1
            continue
        accepted += 1
    store.record_ingestion_job(dataset_id, version, "streaming",
                               received, accepted, duplicates, quarantined)
    store.audit("ingestion_job", dataset_id, "streaming",
                f"v{version}: {accepted} accepted, {duplicates} dup, {quarantined} quarantined")
    return {"received": received, "accepted": accepted,
            "duplicates": duplicates, "quarantined": quarantined}
