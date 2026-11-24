"""Tests for model shapes: params, memory, FLOPs, KV cache."""

import pytest

from inference_optimizer.model import PRESETS, ModelConfig


def test_glm_4b_param_count():
    model = PRESETS["glm-4b"]
    assert 4_000_000_000 < model.param_count() < 4_500_000_000


def test_param_count_exact_small_model():
    model = ModelConfig("t", layers=2, hidden=8, heads=2, vocab=16, intermediate=16)
    per_layer = 4 * 64 + 3 * 8 * 16
    assert model.param_count() == 16 * 8 + 2 * per_layer + 8


def test_weight_gb_fp16_vs_int8():
    model = PRESETS["glm-4b"]
    assert model.weight_gb(2) == pytest.approx(2 * model.weight_gb(1), rel=1e-9)
    assert 7.0 < model.weight_gb(2) < 8.5


def test_kv_bytes_per_token_exact():
    model = PRESETS["glm-4b"]
    # 2 (K+V) * 36 layers * 32 heads * 80 head_dim * 2 bytes
    assert model.kv_bytes_per_token() == 2 * 36 * 32 * 80 * 2


def test_flops_per_token_is_twice_params():
    model = PRESETS["small-2b"]
    assert model.flops_per_token() == 2 * model.param_count()


def test_kv_gb_scales_with_batch_and_seq():
    model = PRESETS["tiny-0.5b"]
    assert model.kv_gb(8, 2048) == pytest.approx(4 * model.kv_gb(2, 2048), rel=1e-9)
    assert model.kv_gb(2, 4096) == pytest.approx(2 * model.kv_gb(2, 2048), rel=1e-9)


def test_head_dim():
    assert PRESETS["glm-4b"].head_dim == 80


def test_hidden_must_divide_across_heads():
    with pytest.raises(ValueError):
        ModelConfig("bad", layers=2, hidden=10, heads=3, vocab=100)


def test_bad_dtype_rejected():
    with pytest.raises(ValueError):
        ModelConfig("bad", layers=2, hidden=8, heads=2, vocab=100, dtype_bytes=3)


def test_non_positive_shape_rejected():
    with pytest.raises(ValueError):
        ModelConfig("bad", layers=0, hidden=8, heads=2, vocab=100)
    with pytest.raises(ValueError):
        ModelConfig("bad", layers=2, hidden=8, heads=2, vocab=0)


def test_kv_gb_bad_batch_rejected():
    with pytest.raises(ValueError):
        PRESETS["tiny-0.5b"].kv_gb(0, 128)


def test_all_presets_have_positive_params():
    for name, model in PRESETS.items():
        assert model.param_count() > 0, name
        assert model.weight_gb() > 0, name
