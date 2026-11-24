"""Tests for the end-to-end profiler."""

import pytest

from inference_optimizer.model import PRESETS
from inference_optimizer.profiler import HARDWARE_PRESETS, compare_configs, profile


def test_glm_fits_on_80gb():
    result = profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                     batch=8, seq_len=2048)
    assert result["fits"] is True
    assert 7.0 < result["weight_gb"] < 8.5
    assert result["total_gb"] < 80
    assert result["throughput_tokens_per_sec"] > 0


def test_kimi_fp16_does_not_fit_16gb():
    result = profile(PRESETS["kimi-8b"], HARDWARE_PRESETS["accel-16gb"],
                     batch=1, seq_len=512)
    assert result["fits"] is False
    assert result["weight_gb"] > 16


def test_int8_halves_weight_memory():
    fp16 = profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                   batch=8, seq_len=2048, dtype_bytes=2)
    int8 = profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                   batch=8, seq_len=2048, dtype_bytes=1)
    assert int8["weight_gb"] == pytest.approx(fp16["weight_gb"] / 2, rel=1e-3)


def test_int8_is_faster_than_fp16_when_memory_bound():
    fp16 = profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                   batch=8, seq_len=2048, dtype_bytes=2)
    int8 = profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                   batch=8, seq_len=2048, dtype_bytes=1)
    assert int8["throughput_tokens_per_sec"] >= fp16["throughput_tokens_per_sec"]


def test_tp_splits_weight_memory():
    single = profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                     batch=8, seq_len=2048, tp_devices=1)
    sharded = profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                      batch=8, seq_len=2048, tp_devices=2)
    assert sharded["weight_gb"] == pytest.approx(single["weight_gb"] / 2, rel=0.01)


def test_compare_configs_ranks_fitting_first():
    ranked = compare_configs(
        PRESETS["kimi-8b"], HARDWARE_PRESETS["accel-16gb"], batch=1, seq_len=512,
        candidates=[(2, 1), (1, 1), (1, 2), (1, 4)],
    )
    assert ranked[0]["fits"] is True
    assert ranked[-1]["fits"] is False


def test_compare_configs_sorted_by_throughput():
    ranked = compare_configs(
        PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"], batch=8, seq_len=2048,
        candidates=[(2, 1), (1, 1), (2, 2), (1, 2)],
    )
    fitting = [r for r in ranked if r["fits"]]
    throughputs = [r["throughput_tokens_per_sec"] for r in fitting]
    assert throughputs == sorted(throughputs, reverse=True)


def test_bound_is_reported():
    result = profile(PRESETS["tiny-0.5b"], HARDWARE_PRESETS["accel-80gb"],
                     batch=1, seq_len=128)
    assert result["bound"] in ("compute", "memory")


def test_invalid_batch_rejected():
    with pytest.raises(ValueError):
        profile(PRESETS["glm-4b"], HARDWARE_PRESETS["accel-80gb"],
                batch=0, seq_len=128)
