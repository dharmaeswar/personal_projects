"""Cluster and cost advisor for Databricks Spark jobs.

Pure arithmetic over job statistics — no cloud calls. It turns a run's
measured input size, shuffle size, duration and worker count into
concrete tuning actions: target partition size, worker count, and an
estimated DBU cost, plus a skew flag when one partition dwarfs the rest.
"""
from __future__ import annotations

TARGET_FILE_MB = 128
DBU_RATE_PER_HOUR = 0.40  # example all-purpose-compute rate; config, not a bill


def recommend_partitions(input_gb: float,
                         target_mb: float = TARGET_FILE_MB) -> int:
    """Partitions so each output file lands near the target size."""
    if input_gb <= 0:
        raise ValueError("input_gb must be positive")
    return max(1, round(input_gb * 1024 / target_mb))


def detect_skew(partition_sizes_gb: list[float]) -> dict:
    """Flag skew when the largest partition is far above the median.

    Mirrors the check a tuned job runs on stage metrics: a max/median
    ratio above 3 means one key (or one title) is starving the cluster.
    """
    if not partition_sizes_gb:
        raise ValueError("partition_sizes_gb must not be empty")
    ordered = sorted(partition_sizes_gb)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    ratio = (max(ordered) / median) if median > 0 else float("inf")
    return {
        "max_gb": max(ordered),
        "median_gb": round(median, 3),
        "max_median_ratio": round(ratio, 2),
        "skewed": ratio > 3,
        "recommendation": ("Salt the hot key or repartition on a finer key"
                           if ratio > 3 else "No action needed"),
    }


def estimate_cost(dbu_per_hour: float, hours: float, workers: int) -> dict:
    """Estimate the DBU cost of a job run from its worker-hours."""
    if dbu_per_hour < 0 or hours < 0 or workers < 1:
        raise ValueError("dbu_per_hour and hours must be >= 0, workers >= 1")
    dbus = round(dbu_per_hour * hours * workers, 2)
    return {"dbus": dbus, "cost_usd": round(dbus * DBU_RATE_PER_HOUR, 2),
            "worker_hours": round(hours * workers, 2)}


def advise(job_stats: dict) -> dict:
    """One-pass tuning advice from a finished run's stats.

    job_stats: input_gb, shuffle_gb, duration_minutes, workers,
    partition_sizes_gb. Returns recommendations a job owner can act on.
    """
    workers = job_stats["workers"]
    duration_h = job_stats["duration_minutes"] / 60
    partitions = recommend_partitions(job_stats["input_gb"])
    skew = detect_skew(job_stats["partition_sizes_gb"])
    cost = estimate_cost(DBU_RATE_PER_HOUR, duration_h, workers)
    recs: list[str] = []
    if skew["skewed"]:
        recs.append(f"Fix skew: {skew['recommendation']}")
    if job_stats["shuffle_gb"] > job_stats["input_gb"]:
        recs.append("Shuffle exceeds input: add a broadcast join for the "
                    "small dimension or filter before the join")
    if duration_h > 1 and workers < 4:
        recs.append("Long run on few workers: enable autoscaling "
                    "(min 2, max 8 workers) instead of a fixed cluster")
    recs.append(f"Set spark.sql.shuffle.partitions={partitions} so output "
                f"files land near {TARGET_FILE_MB} MB")
    return {"recommended_partitions": partitions, "skew": skew,
            "cost": cost, "recommendations": recs}
