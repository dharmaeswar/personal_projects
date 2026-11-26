"""Orchestration: an Airflow-style DAG plus a Databricks Workflows job spec.

The DAG runs the pipeline stages in dependency order with retries; the
Workflows builder emits the JSON a Databricks job of the same stages
would carry (tasks, job cluster, schedule). Nothing here calls a cloud
API — the spec is a config artifact the run manifest records.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import cost as cost_mod
from . import events as events_mod
from . import governance as gov_mod
from . import quality as quality_mod
from . import streaming as stream_mod
from . import warehouse as wh_mod


@dataclass
class Task:
    name: str
    fn: object  # callable[[dict], dict]
    depends_on: list[str] = field(default_factory=list)
    retries: int = 1


@dataclass
class Dag:
    name: str
    tasks: list[Task] = field(default_factory=list)

    def run(self, context: dict | None = None) -> dict:
        """Run tasks in dependency order; retry a failed task, then fail loud."""
        ctx: dict = dict(context or {})
        done: dict[str, dict] = {}
        remaining = list(self.tasks)
        while remaining:
            progressed = False
            for task in list(remaining):
                if any(d not in done for d in task.depends_on):
                    continue
                last_error: Exception | None = None
                for attempt in range(task.retries + 1):
                    try:
                        t0 = time.monotonic()
                        result = task.fn(ctx)
                        done[task.name] = {
                            "status": "success", "attempt": attempt + 1,
                            "duration_s": round(time.monotonic() - t0, 3),
                            "result": result,
                        }
                        ctx[task.name] = result
                        break
                    except Exception as exc:  # noqa: BLE001 - retry then record
                        last_error = exc
                else:
                    done[task.name] = {"status": "failed",
                                       "error": str(last_error)}
                    raise RuntimeError(
                        f"DAG task {task.name} failed after "
                        f"{task.retries + 1} attempts: {last_error}") from last_error
                remaining.remove(task)
                progressed = True
            if not progressed:
                missing = [t.name for t in remaining]
                raise RuntimeError(f"DAG has an unmet dependency: {missing}")
        return {"dag": self.name, "tasks": done}


def databricks_workflow_job(name: str, task_names: list[str],
                            cluster_workers: int = 2,
                            schedule_cron: str = "0 * * * *") -> dict:
    """Build a Databricks Workflows job spec for these pipeline stages."""
    if cluster_workers < 1:
        raise ValueError("cluster_workers must be >= 1")
    tasks = []
    for i, tname in enumerate(task_names):
        task: dict = {
            "task_key": tname,
            "job_cluster_key": "session-streaming-cluster",
            "spark_python_task": {
                "python_file": "/Workspace/session-streaming/run_pipeline.py",
                "parameters": ["--stage", tname],
            },
            "timeout_seconds": 3600,
            "max_retries": 1,
        }
        if i > 0:
            task["depends_on"] = [{"task_key": task_names[i - 1]}]
        tasks.append(task)
    return {
        "name": name,
        "job_clusters": [{
            "job_cluster_key": "session-streaming-cluster",
            "new_cluster": {
                "spark_version": "15.4.x-scala2.12",
                "node_type_id": "i3.xlarge",
                "num_workers": cluster_workers,
                "autoscale": {"min_workers": 2, "max_workers": 8},
                "spark_conf": {
                    "spark.sql.shuffle.partitions": "200",
                    "spark.databricks.delta.optimizeWrite.enabled": "true",
                    "spark.databricks.delta.autoCompact.enabled": "true",
                },
            },
        }],
        "tasks": tasks,
        "schedule": {"quartz_cron_expression": schedule_cron,
                     "timezone_id": "UTC"},
    }


def run_pipeline(n_sessions: int = 40, seed: int = 42,
                 out_dir: Path | str = "data") -> dict:
    """Run the full pipeline end to end and return a run manifest."""
    out = Path(out_dir)
    started = datetime.now(timezone.utc)

    def _generate(ctx):
        evs = events_mod.generate_sessions(n_sessions, seed=seed)
        return {"events": len(evs)}

    def _cleanse(ctx):
        evs = events_mod.generate_sessions(n_sessions, seed=seed)
        good, quar = quality_mod.cleanse(evs)
        return {"good": len(good), "quarantined": len(quar),
                "quarantine": [q["quarantine_reason"] for q in quar],
                "events": good}

    def _stream(ctx):
        good = ctx["_cleanse"]["events"]
        df = stream_mod.to_frame(good)
        on_time, late = stream_mod.process_micro_batches(df)
        sessions = stream_mod.sessionize(on_time)
        agg = stream_mod.tumbling_aggregates(on_time)
        return {"on_time": len(on_time), "late": len(late),
                "sessions": len(sessions), "windows": len(agg),
                "session_rows": sessions, "agg_rows": agg}

    def _warehouse(ctx):
        good = ctx["_cleanse"]["events"]
        df = stream_mod.to_frame(good)
        sessions = ctx["_stream"]["session_rows"]
        agg = ctx["_stream"]["agg_rows"]
        bronze = wh_mod.write_bronze(df, out)
        silver = wh_mod.write_silver(df, out)
        gold = wh_mod.write_gold_sessions(sessions, out)
        titles = [{"title_id": t, "title_name": t.replace("-", " ").title(),
                   "genre": "drama"} for t in sorted({e["title_id"] for e in good})]
        dim = wh_mod.build_title_dimension(titles)
        fact = wh_mod.build_session_fact(sessions, dim)
        return {"bronze_files": len(bronze), "silver_files": len(silver),
                "gold_files": len(gold), "fact_rows": len(fact),
                "sessions": sessions, "fact": fact}

    def _govern(ctx):
        catalog = gov_mod.Catalog()
        catalog.register(gov_mod.TableDef(
            "media", "bronze", "raw_session_events",
            ["event_id", "session_id", "user_id", "title_id", "event_type",
             "event_ts", "playhead_seconds", "bitrate_kbps"],
            pii_columns=["user_id"]))
        catalog.register(gov_mod.TableDef(
            "media", "gold", "fact_session",
            ["session_id", "user_id", "title_id", "duration_seconds",
             "event_count", "error_count"],
            pii_columns=["user_id"]))
        catalog.record_lineage("media.bronze.raw_session_events",
                               "media.gold.fact_session",
                               "cleanse -> sessionize -> star-schema join")
        fact = ctx["_warehouse"]["fact"]
        masked = catalog.mask_pii(fact, "media.gold.fact_session")
        return {"tables": len(catalog.tables),
                "lineage_entries": len(catalog.lineage),
                "audit_entries": len(catalog.audit),
                "masked_user_ids": int((masked["user_id"] != fact["user_id"]).sum())
                if len(fact) else 0}

    def _advise(ctx):
        stats = {"input_gb": 0.5, "shuffle_gb": 0.4,
                 "duration_minutes": 12.0, "workers": 2,
                 "partition_sizes_gb": [0.09, 0.11, 0.10, 0.12]}
        return cost_mod.advise(stats)

    dag = Dag("media-session-streaming", tasks=[
        Task("_generate", _generate),
        Task("_cleanse", _cleanse, depends_on=["_generate"]),
        Task("_stream", _stream, depends_on=["_cleanse"]),
        Task("_warehouse", _warehouse, depends_on=["_stream"]),
        Task("_govern", _govern, depends_on=["_warehouse"]),
        Task("_advise", _advise, depends_on=["_govern"]),
    ])
    result = dag.run()
    finished = datetime.now(timezone.utc)
    return {
        "pipeline": "media-session-streaming",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_s": round((finished - started).total_seconds(), 2),
        "events_generated": result["tasks"]["_generate"]["result"]["events"],
        "events_good": result["tasks"]["_cleanse"]["result"]["good"],
        "events_quarantined": result["tasks"]["_cleanse"]["result"]["quarantined"],
        "events_late": result["tasks"]["_stream"]["result"]["late"],
        "sessions": result["tasks"]["_stream"]["result"]["sessions"],
        "windows": result["tasks"]["_stream"]["result"]["windows"],
        "fact_rows": result["tasks"]["_warehouse"]["result"]["fact_rows"],
        "tables_registered": result["tasks"]["_govern"]["result"]["tables"],
        "cost_advice": result["tasks"]["_advise"]["result"],
        "workflow_job": databricks_workflow_job(
            "media-session-streaming",
            ["ingest", "cleanse", "sessionize", "publish"]),
    }
