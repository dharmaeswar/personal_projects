import csv
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from ml_platform.backfill import backfill
from ml_platform.data import generate_applications
from ml_platform.registry import Registry
from ml_platform.training import train_pipeline


def test_backfill_writes_one_row_per_application(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    model, metrics, _ = train_pipeline(n_train=500, n_test=100, seed=42)
    version = registry.register("credit-decision", model, metrics)
    out_path = str(tmp_path / "backfill.csv")
    path, n, mean_p = backfill(registry, version, generate_applications(50, seed=5), out_path)
    assert path == out_path and n == 50
    assert 0.0 <= mean_p <= 1.0
    with open(out_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 50
    assert all(r["version"] == version for r in rows)
    assert all(r["decision"] in ("approve", "decline") for r in rows)
    assert all(0.0 <= float(r["default_probability"]) <= 1.0 for r in rows)


def test_backfill_unknown_version_fails(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    with pytest.raises(ValueError):
        backfill(registry, "no-such-version", generate_applications(5, seed=1),
                 str(tmp_path / "out.csv"))
