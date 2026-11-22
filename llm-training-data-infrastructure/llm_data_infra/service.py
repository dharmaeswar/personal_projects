"""Dashboard aggregates: catalog stats, dedup/quality rates, job health."""
from .store import Store


def dataset_stats(store: Store, dataset_id: int) -> dict:
    ds = store.get_dataset(dataset_id)
    if ds is None:
        raise ValueError(f"unknown dataset id {dataset_id}")
    records = store.list_records(dataset_id)
    accepted = [r for r in records if r["status"] == "accepted"]
    quarantined = [r for r in records if r["status"] == "quarantined"]
    jobs = store.list_ingestion_jobs(dataset_id)
    total_received = sum(j["received"] for j in jobs)
    total_dup = sum(j["duplicates"] for j in jobs)
    checks = store.list_quality_checks(dataset_id)
    return {
        "dataset_id": dataset_id,
        "name": ds["name"],
        "modality": ds["modality"],
        "versions": [v["version"] for v in store.list_versions(dataset_id)],
        "records": len(records),
        "accepted": len(accepted),
        "quarantined": len(quarantined),
        "dedup_rate": (total_dup / total_received) if total_received else 0.0,
        "quality_failures": sum(c["failed"] for c in checks),
        "lineage_edges": len(store.list_lineage(dataset_id)),
    }


def dashboard(store: Store) -> dict:
    datasets = store.list_datasets()
    jobs = store.list_ingestion_jobs()
    total_received = sum(j["received"] for j in jobs)
    total_accepted = sum(j["accepted"] for j in jobs)
    total_dup = sum(j["duplicates"] for j in jobs)
    total_quar = sum(j["quarantined"] for j in jobs)
    return {
        "datasets": [dataset_stats(store, d["id"]) for d in datasets],
        "ingestion": {
            "jobs": len(jobs),
            "received": total_received,
            "accepted": total_accepted,
            "duplicates": total_dup,
            "quarantined": total_quar,
            "accept_rate": (total_accepted / total_received) if total_received else 0.0,
        },
        "pipeline_health": (
            "healthy" if total_quar <= max(1, total_received // 20) else "needs_attention"
        ),
    }
