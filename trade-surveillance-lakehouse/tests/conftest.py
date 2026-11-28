"""Shared fixture: build the whole lakehouse once per test module."""
from __future__ import annotations

from pathlib import Path

import pytest

from surveillance_lakehouse import cat as cat_mod
from surveillance_lakehouse import generate as gen
from surveillance_lakehouse import gold as gold_mod
from surveillance_lakehouse import ingest as ingest_mod
from surveillance_lakehouse import model as model_mod
from surveillance_lakehouse import snapshots as snap
from surveillance_lakehouse import tuning as tuning_mod


@pytest.fixture(scope="module")
def lakehouse(tmp_path_factory):
    root = Path(tmp_path_factory.mktemp("lakehouse"))
    bronze, silver, gold = root / "bronze", root / "silver", root / "gold"
    feeds = gen.generate()
    bronze_report = {}
    for name, df in feeds.items():
        bronze_report[name] = ingest_mod.ingest(name, df, bronze)
        snap.record_snapshot(bronze / name, "append",
                             bronze_report[name]["rows_written"])
    silver_report = model_mod.build_silver(bronze, silver)
    tuning_mod.write_partitioned_trades(silver)
    dq = gold_mod.build_gold(silver, gold)
    cat_result = cat_mod.export_cat(gold, root / "cat_report.txt")
    tuning_result = tuning_mod.tune(silver, root / "tuning_report.md")
    return {"root": root, "bronze": bronze, "silver": silver, "gold": gold,
            "feeds": feeds, "bronze_report": bronze_report,
            "silver_report": silver_report, "dq": dq,
            "cat": cat_result, "tuning": tuning_result}
