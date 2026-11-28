"""Tests for Glue-style ETL jobs and Iceberg-style snapshot targets."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.data import (
    generate_customers,
    generate_orders,
    generate_products,
    plant_violations,
)
from lakehouse.glue_etl import GlueJob, run_glue_job, seed_partitions
from lakehouse.snapshots import current_snapshot, list_snapshots, read_snapshot


def _job(tmp_path):
    return GlueJob(
        name="orders-load",
        source_dir=tmp_path / "bronze",
        target_table_dir=tmp_path / "silver",
        bookmark_path=tmp_path / "bookmark.json",
        quarantine_dir=tmp_path / "quarantine",
    )


def test_seed_partitions_writes_date_layout(tmp_path):
    frames = {"2026-11-15": generate_orders(seed=1), "2026-11-16": generate_orders(seed=2)}
    names = seed_partitions(tmp_path / "bronze", frames)
    assert names == ["date=2026-11-15", "date=2026-11-16"]
    assert (tmp_path / "bronze" / "date=2026-11-15" / "orders.parquet").exists()
    assert len(pd.read_parquet(tmp_path / "bronze" / "date=2026-11-15" / "orders.parquet")) == len(
        frames["2026-11-15"]
    )


def test_job_lists_partitions_sorted(tmp_path):
    seed_partitions(
        tmp_path / "bronze",
        {"2026-11-17": generate_orders(seed=1), "2026-11-15": generate_orders(seed=2)},
    )
    assert _job(tmp_path).list_partitions() == ["date=2026-11-15", "date=2026-11-17"]


def test_job_loads_and_commits_snapshot(tmp_path):
    job = _job(tmp_path)
    seed_partitions(job.source_dir, {"2026-11-15": generate_orders(seed=11)})
    run = run_glue_job(job, generate_customers(), generate_products())
    assert run.status == "loaded"
    assert run.rows_read == 200
    assert run.rows_loaded == 200
    assert run.rows_quarantined == 0
    assert run.snapshot_id == 1
    assert run.bookmark == "date=2026-11-15"
    assert current_snapshot(job.target_table_dir)["rows"] == 200


def test_job_quarantines_bad_rows(tmp_path):
    job = _job(tmp_path)
    seed_partitions(job.source_dir, {"2026-11-16": plant_violations(generate_orders(seed=12))})
    run = run_glue_job(job, generate_customers(), generate_products())
    assert run.status == "loaded"
    assert run.rows_read == 200
    assert run.rows_quarantined == 13
    assert run.rows_loaded == 200 - 13
    q = pd.read_parquet(job.quarantine_dir / "orders.parquet")
    assert len(q) == 13
    assert "quarantine_reason" in q.columns


def test_job_bookmark_makes_second_run_a_noop(tmp_path):
    job = _job(tmp_path)
    seed_partitions(job.source_dir, {"2026-11-15": generate_orders(seed=11)})
    first = run_glue_job(job, generate_customers(), generate_products())
    second = run_glue_job(job, generate_customers(), generate_products())
    assert first.status == "loaded"
    assert second.status == "no_new_partitions"
    assert second.snapshot_id is None
    assert len(list_snapshots(job.target_table_dir)) == 1


def test_job_processes_only_new_partitions(tmp_path):
    job = _job(tmp_path)
    seed_partitions(job.source_dir, {"2026-11-15": generate_orders(seed=11)})
    run_glue_job(job, generate_customers(), generate_products())
    seed_partitions(job.source_dir, {"2026-11-16": generate_orders(seed=12)})
    run = run_glue_job(job, generate_customers(), generate_products())
    assert run.partitions_read == ["date=2026-11-16"]
    assert run.snapshot_id == 2
    # Same order ids across seeds dedupe to one row per order.
    silver = read_snapshot(job.target_table_dir, 2)
    assert silver["order_id"].is_unique


def test_job_on_empty_source_is_noop(tmp_path):
    job = _job(tmp_path)
    run = run_glue_job(job, generate_customers(), generate_products())
    assert run.status == "no_new_partitions"
    assert list_snapshots(job.target_table_dir) == []
