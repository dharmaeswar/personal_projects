import json

import pandas as pd

from personalization_data import datasets, events, features, quality


def _rows():
    raw = events.generate_events(n_impressions=120, seed=42)
    clean, _ = quality.cleanse(raw)
    return raw, clean, features.build_training_rows(clean)


def test_time_split_is_temporal_and_disjoint():
    _, _, rows = _rows()
    splits = datasets.time_split(rows)
    assert set(splits) == {"train", "validation", "test"}
    assert sum(len(v) for v in splits.values()) == len(rows)
    train_max = splits["train"]["impression_ts"].max()
    val_min = splits["validation"]["impression_ts"].min()
    test_min = splits["test"]["impression_ts"].min()
    assert train_max < val_min
    assert splits["validation"]["impression_ts"].max() < test_min


def test_fingerprint_is_stable_and_config_sensitive():
    _, _, rows = _rows()
    cfg = {"version": "v1"}
    assert datasets.dataset_fingerprint(rows, cfg) == datasets.dataset_fingerprint(rows, cfg)
    assert datasets.dataset_fingerprint(rows, cfg) != datasets.dataset_fingerprint(rows, {"version": "v2"})


def test_medallion_writes_and_manifest(tmp_path):
    raw, clean, rows = _rows()
    manifest = datasets.write_medallion(raw, clean, rows, tmp_path)
    assert (tmp_path / "bronze" / "events.parquet").exists()
    assert (tmp_path / "silver" / "events.parquet").exists()
    assert (tmp_path / "gold" / "training_dataset.parquet").exists()
    saved = json.loads((tmp_path / "gold" / "manifest.json").read_text())
    assert saved == manifest
    assert manifest["row_counts"]["bronze"] == len(raw)
    assert manifest["row_counts"]["silver"] == len(clean)
    assert manifest["row_counts"]["gold"] == len(rows)
    assert len(manifest["fingerprint"]) == 16
    gold = pd.read_parquet(tmp_path / "gold" / "training_dataset.parquet")
    assert len(gold) == len(rows)
