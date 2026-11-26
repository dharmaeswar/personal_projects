"""Cost and performance advice for the pipeline.

Mirrors what a data engineer checks in the Spark UI and Databricks DBU
usage reports: partition skew, file sizes against the 128 MB target, and
the estimated DBU cost of the daily job. All numbers are estimates from
the local run's row counts — no real cluster or cloud bill is involved.
"""

from __future__ import annotations

import pandas as pd

TARGET_FILE_MB = 128.0
DBU_PER_HOUR = 0.40  # i3.xlarge job-compute DBU rate used for the estimate
AVG_ROW_BYTES = 220  # measured mean row size of the Parquet event rows


def advise(df: pd.DataFrame, partition_col: str = "content_id",
           hours: float = 0.5, workers: int = 2) -> dict:
    """Estimate size, skew, and cost for a DataFrame headed to a table."""
    if df.empty:
        return {"rows": 0, "estimated_mb": 0.0, "skew_ratio": 0.0,
                "estimated_dbu": 0.0, "advice": ["empty input: nothing to write"]}
    estimated_mb = round(len(df) * AVG_ROW_BYTES / (1024 * 1024), 2)
    counts = df.groupby(partition_col).size()
    skew_ratio = round(float(counts.max() / counts.median()), 2) if len(counts) else 0.0
    files = max(1, round(estimated_mb / TARGET_FILE_MB)) if estimated_mb else 1
    estimated_dbu = round(hours * workers * DBU_PER_HOUR, 2)
    advice: list[str] = []
    if skew_ratio > 3:
        advice.append(
            f"skew detected on {partition_col} (max/median {skew_ratio}x): "
            "salt the hot partition key or repartition before writing")
    if estimated_mb > TARGET_FILE_MB * 4:
        advice.append(
            f"estimated {estimated_mb} MB across {files} target files: "
            "raise shuffle partitions so no single file exceeds the target")
    if not advice:
        advice.append("partition sizes look balanced; no tuning action needed")
    return {
        "rows": len(df),
        "estimated_mb": estimated_mb,
        "skew_ratio": skew_ratio,
        "target_files": files,
        "estimated_dbu": estimated_dbu,
        "advice": advice,
    }
