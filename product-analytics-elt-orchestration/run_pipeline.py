"""End-to-end pipeline run: seed events, run the DAG, print the report.

Usage: python run_pipeline.py [--db PATH] [--events N]

Steps (each a DAG task with dependencies):
  validate_and_load -> build_staging -> build_sessions -> compute_metrics
  -> experiment_checks -> quality_checks -> publish_catalog
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from product_analytics import catalog, db, experiments, ingest, metrics, models, quality, seed, transforms
from product_analytics.orchestration import Task, run_dag

LATEST_DATE = "2026-11-14"
EXPERIMENT_START = "2026-11-08"


def build_tasks(events: list[dict]) -> list[Task]:
    def load(conn):
        return ingest.load_raw(conn, events)

    def stage(conn):
        return ingest.build_staging(conn)

    def sessions(conn):
        return transforms.build_sessions(conn)

    def compute_metrics(conn):
        return metrics.compute_all(conn, LATEST_DATE)

    def experiment_checks(conn):
        return experiments.run_experiment_checks(
            conn, experiments.DEFAULT_EXPERIMENT, EXPERIMENT_START, LATEST_DATE
        )

    def checks(conn):
        results = quality.run_checks(conn, LATEST_DATE)
        if not quality.all_passed(results):
            failed = [c["check"] for c in results if c["status"] == "fail"]
            raise RuntimeError(f"quality checks failed: {failed}")
        return results

    def build_models(conn):
        return models.build_models(conn, LATEST_DATE)

    def publish(conn):
        catalog.generate(conn, os.path.join(os.path.dirname(__file__), "CATALOG.md"))
        return {"catalog": "CATALOG.md"}

    return [
        Task("validate_and_load", load),
        Task("build_staging", stage, ("validate_and_load",)),
        Task("build_sessions", sessions, ("build_staging",)),
        Task("compute_metrics", compute_metrics, ("build_sessions",)),
        Task("experiment_checks", experiment_checks, ("compute_metrics",)),
        Task("quality_checks", checks, ("experiment_checks",)),
        Task("build_models", build_models, ("quality_checks",)),
        Task("publish_catalog", publish, ("build_models",)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=":memory:")
    parser.add_argument("--events", type=int, default=6000)
    args = parser.parse_args()

    conn = db.connect(args.db)
    events = seed.generate_events(count=args.events)
    results = run_dag(conn, build_tasks(events))
    print("DAG results:")
    for name, status in results.items():
        print(f"  {name}: {status}")
    dau = transforms.dau(conn, LATEST_DATE)
    funnel = transforms.funnel(conn, LATEST_DATE)
    print(f"DAU {LATEST_DATE}: {dau}")
    print(f"Funnel {LATEST_DATE}: viewed={funnel['viewers']} saved={funnel['savers']} "
          f"clicked={funnel['clickers']}")
    print("Experiment guardrails:")
    for row in conn.execute(
        "SELECT check_name, status, detail FROM experiment_results ORDER BY check_name"
    ):
        print(f"  {row[0]}: {row[1]} — {row[2]}")
    print("Catalog written to CATALOG.md")
    print("Model tests:")
    for row in conn.execute(
        "SELECT model_name, test_name, status, detail FROM model_test_results ORDER BY model_name"
    ):
        print(f"  {row[0]}.{row[1]}: {row[2]} — {row[3]}")
    print("Model docs written to MODELS.md")
    return 0 if all(s == "success" for s in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
