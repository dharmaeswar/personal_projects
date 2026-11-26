"""Orchestration: Airflow-style DAG, Databricks Workflows spec, Glue catalog.

The daily job is a DAG — ingest -> cleanse -> features -> model -> publish —
with one retry per failed task and downstream tasks skipped on failure. The
same job is expressible as a Databricks Workflows multi-task job and
registered in the AWS Glue Data Catalog so Athena / Redshift Spectrum can
query the gold tables.

These builders emit plain dicts/JSON; they do not call Airflow, Databricks,
or AWS, so the project runs anywhere.
"""

from __future__ import annotations

import json

TASKS = [
    {"name": "ingest_raw_events", "depends_on": [], "retries": 1},
    {"name": "cleanse_bronze_to_silver", "depends_on": ["ingest_raw_events"], "retries": 1},
    {"name": "build_training_features", "depends_on": ["cleanse_bronze_to_silver"], "retries": 1},
    {"name": "build_star_schema", "depends_on": ["cleanse_bronze_to_silver"], "retries": 1},
    {"name": "publish_gold_dataset", "depends_on": ["build_training_features", "build_star_schema"], "retries": 2},
    {"name": "quality_report", "depends_on": ["publish_gold_dataset"], "retries": 0},
]


def topological_order(tasks: list[dict]) -> list[str]:
    """Order tasks so every dependency runs first; raises on a cycle."""
    order: list[str] = []
    remaining = {t["name"]: set(t["depends_on"]) for t in tasks}
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:
            raise ValueError(f"dependency cycle among: {sorted(remaining)}")
        for name in ready:
            order.append(name)
            del remaining[name]
            for deps in remaining.values():
                deps.discard(name)
    return order


class DagRun:
    """Minimal Airflow-style runner: executes tasks in order, one retry each."""

    def __init__(self, tasks: list[dict], handlers: dict):
        self.tasks = {t["name"]: t for t in tasks}
        self.handlers = handlers
        self.attempts: dict[str, list[str]] = {}

    def run(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for name in topological_order(list(self.tasks.values())):
            task = self.tasks[name]
            if any(results.get(dep) != "success" for dep in task["depends_on"]):
                results[name] = "skipped"
                self.attempts[name] = ["skipped: upstream failed"]
                continue
            outcomes: list[str] = []
            status = "failed"
            for attempt in range(task["retries"] + 1):
                try:
                    self.handlers[name]()
                    status = "success"
                    outcomes.append(f"attempt {attempt + 1}: success")
                    break
                except Exception as exc:  # noqa: BLE001 - record and retry
                    outcomes.append(f"attempt {attempt + 1}: failed ({exc})")
            results[name] = status
            self.attempts[name] = outcomes
        return results


def databricks_job_spec(job_name: str = "personalization-training-datasets",
                        schedule: str = "0 2 * * *") -> dict:
    """Databricks Workflows multi-task job spec for the same DAG."""
    return {
        "name": job_name,
        "schedule": {"quartz_cron_expression": schedule, "timezone_id": "America/Los_Angeles"},
        "job_clusters": [{
            "job_cluster_key": "pipeline_cluster",
            "new_cluster": {
                "spark_version": "15.4.x-gpu-ml-scala2.12",
                "node_type_id": "i3.xlarge",
                "num_workers": 2,
                "autoscale": {"min_workers": 1, "max_workers": 8},
                "spark_conf": {"spark.sql.adaptive.enabled": "true"},
            },
        }],
        "tasks": [
            {"task_key": t["name"], "job_cluster_key": "pipeline_cluster",
             "depends_on": [{"task_key": d} for d in t["depends_on"]],
             "spark_python_task": {"python_file": f"/Workspace/personalization/{t['name']}.py"}}
            for t in TASKS
        ],
    }


def glue_catalog(database: str = "personalization_ml") -> dict:
    """AWS Glue Data Catalog entries for the medallion tables."""
    return {
        "database": database,
        "tables": {
            "bronze_events": {
                "location": "s3://disney-ml-lakehouse/bronze/events/",
                "partition_keys": ["event_date"],
                "columns": ["event_id", "user_id", "content_id", "event_type",
                            "event_ts", "ingested_at", "device", "surface",
                            "country", "genre", "title_type",
                            "content_duration_s", "watch_seconds"],
            },
            "silver_events": {
                "location": "s3://disney-ml-lakehouse/silver/events/",
                "partition_keys": ["event_date"],
                "columns": ["event_id", "user_id", "content_id", "event_type",
                            "event_ts", "device", "surface", "country", "genre",
                            "title_type", "content_duration_s", "watch_seconds"],
            },
            "gold_training_dataset": {
                "location": "s3://disney-ml-lakehouse/gold/training_dataset/",
                "partition_keys": ["impression_date"],
                "columns": ["user_id", "content_id", "impression_ts",
                            "label_completed", "label_liked", "user_prior_views",
                            "user_prior_completions", "user_avg_watch_ratio",
                            "content_prior_7d_views", "content_duration_s",
                            "genre", "title_type", "device", "surface"],
            },
        },
    }


def dag_as_json() -> str:
    """Pretty JSON of the DAG definition, for docs and review."""
    return json.dumps({"tasks": TASKS}, indent=2)
