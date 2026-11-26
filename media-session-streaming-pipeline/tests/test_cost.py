import pytest

from session_stream.cost import (
    advise, detect_skew, estimate_cost, recommend_partitions,
)


def test_recommend_partitions_scales_with_input():
    assert recommend_partitions(1.0) == 8  # 1024 MB / 128 MB
    assert recommend_partitions(16.0) == 128
    assert recommend_partitions(0.01) == 1


def test_recommend_partitions_rejects_non_positive():
    with pytest.raises(ValueError):
        recommend_partitions(0)


def test_detect_skew_flags_hot_partition():
    result = detect_skew([0.1, 0.1, 0.1, 5.0])
    assert result["skewed"] is True
    assert result["max_median_ratio"] == 50.0
    assert "Salt" in result["recommendation"]


def test_detect_skew_balanced_is_fine():
    result = detect_skew([0.10, 0.11, 0.09, 0.12])
    assert result["skewed"] is False
    assert result["recommendation"] == "No action needed"


def test_detect_skew_empty_raises():
    with pytest.raises(ValueError):
        detect_skew([])


def test_estimate_cost_math():
    result = estimate_cost(0.40, 2.0, 4)
    assert result["dbus"] == 3.2
    assert result["worker_hours"] == 8.0
    assert result["cost_usd"] == round(3.2 * 0.40, 2)


def test_estimate_cost_rejects_bad_inputs():
    with pytest.raises(ValueError):
        estimate_cost(0.40, 1.0, 0)
    with pytest.raises(ValueError):
        estimate_cost(-1.0, 1.0, 2)


def test_advise_returns_partitions_skew_cost_and_recs():
    stats = {"input_gb": 8.0, "shuffle_gb": 2.0, "duration_minutes": 30.0,
             "workers": 2, "partition_sizes_gb": [0.5, 0.5, 0.5, 4.0]}
    out = advise(stats)
    assert out["recommended_partitions"] == 64
    assert out["skew"]["skewed"] is True
    assert out["cost"]["dbus"] > 0
    assert any("skew" in r.lower() for r in out["recommendations"])
    assert any("shuffle.partitions" in r for r in out["recommendations"])


def test_advise_flags_shuffle_larger_than_input():
    stats = {"input_gb": 1.0, "shuffle_gb": 5.0, "duration_minutes": 10.0,
             "workers": 2, "partition_sizes_gb": [0.5, 0.5]}
    out = advise(stats)
    assert any("Shuffle exceeds input" in r for r in out["recommendations"])


def test_advise_suggests_autoscaling_for_long_small_runs():
    stats = {"input_gb": 1.0, "shuffle_gb": 0.5, "duration_minutes": 90.0,
             "workers": 2, "partition_sizes_gb": [0.5, 0.5]}
    out = advise(stats)
    assert any("autoscaling" in r for r in out["recommendations"])
