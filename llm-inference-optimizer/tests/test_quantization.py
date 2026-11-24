"""Tests for INT8 quantization and the accuracy-parity check."""

import pytest

from inference_optimizer.quantization import (
    accuracy_parity,
    cosine_similarity,
    dequantize_int8,
    dequantize_rows_int8,
    max_abs_error,
    quantize_int8,
    quantize_rows_int8,
)


def test_roundtrip_error_bounded_by_half_scale():
    values = [0.5, -1.25, 2.0, -0.125, 0.0, 3.75]
    codes, scale = quantize_int8(values)
    recon = dequantize_int8(codes, scale)
    assert max_abs_error(values, recon) <= scale / 2 + 1e-9


def test_codes_within_int8_range():
    values = [100.0, -100.0, 0.01, -0.01]
    codes, _ = quantize_int8(values)
    assert all(-127 <= c <= 127 for c in codes)
    assert max(codes) == 127
    assert min(codes) == -127


def test_scale_is_max_over_127():
    values = [1.27, -0.635, 0.0]
    _, scale = quantize_int8(values)
    assert scale == pytest.approx(1.27 / 127)


def test_all_zeros_roundtrip():
    codes, scale = quantize_int8([0.0, 0.0, 0.0])
    assert codes == [0, 0, 0]
    assert scale == 1.0
    assert dequantize_int8(codes, scale) == [0.0, 0.0, 0.0]


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        quantize_int8([])


def test_per_row_scales_differ():
    matrix = [[0.01, -0.01, 0.02], [10.0, -9.0, 8.0]]
    codes, scales = quantize_rows_int8(matrix)
    assert scales[0] < scales[1]
    recon = dequantize_rows_int8(codes, scales)
    for orig_row, recon_row, scale in zip(matrix, recon, scales):
        assert max_abs_error(orig_row, recon_row) <= scale / 2 + 1e-9


def test_cosine_similarity_identical_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_accuracy_parity_passes_with_loose_tolerance():
    values = [0.3, -0.9, 1.4, 0.05]
    codes, scale = quantize_int8(values)
    recon = dequantize_int8(codes, scale)
    passes, error, cosine = accuracy_parity(values, recon, tolerance=0.05)
    assert passes is True
    assert error <= 0.05
    assert cosine > 0.999


def test_accuracy_parity_fails_with_tiny_tolerance():
    values = [0.3, -0.9, 1.4, 0.05]
    codes, scale = quantize_int8(values)
    recon = dequantize_int8(codes, scale)
    passes, error, _ = accuracy_parity(values, recon, tolerance=1e-9)
    assert passes is False
    assert error > 0


def test_max_abs_error_length_mismatch_rejected():
    with pytest.raises(ValueError):
        max_abs_error([1.0, 2.0], [1.0])
