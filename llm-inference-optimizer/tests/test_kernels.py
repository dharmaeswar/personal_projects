"""Tests for the kernel cost models."""

import math
import random

import pytest

from inference_optimizer.kernels import (
    KernelSpec,
    attention_scores,
    matmul_bytes,
    matmul_flops,
    matmul_naive,
    matmul_tiled,
    roofline_time_ms,
)


def _matrix(rows, cols, seed):
    rng = random.Random(seed)
    return [[rng.uniform(-1, 1) for _ in range(cols)] for _ in range(rows)]


def test_tiled_matches_naive():
    a = _matrix(12, 20, 1)
    b = _matrix(20, 9, 2)
    expected = matmul_naive(a, b)
    for tile in (1, 4, 8, 64):
        got = matmul_tiled(a, b, tile=tile)
        for row_e, row_g in zip(expected, got):
            for x, y in zip(row_e, row_g):
                assert x == pytest.approx(y)


def test_tiled_square_matches_naive():
    a = _matrix(16, 16, 3)
    b = _matrix(16, 16, 4)
    expected = matmul_naive(a, b)
    got = matmul_tiled(a, b, tile=5)
    for row_e, row_g in zip(expected, got):
        assert row_e == pytest.approx(row_g)


def test_matmul_known_values():
    a = [[1.0, 2.0], [3.0, 4.0]]
    b = [[5.0, 6.0], [7.0, 8.0]]
    assert matmul_naive(a, b) == [[19.0, 22.0], [43.0, 50.0]]


def test_matmul_flops_and_bytes():
    assert matmul_flops(2, 3, 4) == 48
    assert matmul_bytes(2, 3, 4, dtype_bytes=2) == (8 + 12 + 6) * 2


def test_ragged_matrix_rejected():
    with pytest.raises(ValueError):
        matmul_naive([[1.0, 2.0], [3.0]], [[1.0], [2.0]])
    with pytest.raises(ValueError):
        matmul_tiled([[1.0, 2.0], [3.0]], [[1.0], [2.0]])


def test_bad_tile_rejected():
    with pytest.raises(ValueError):
        matmul_tiled([[1.0]], [[1.0]], tile=0)


def test_roofline_compute_bound():
    # Huge compute, tiny traffic: compute time dominates.
    spec = KernelSpec("compute-heavy", flops=10**12, bytes_moved=10**6)
    assert roofline_time_ms(spec, peak_tflops=100, bandwidth_gbs=1000) == pytest.approx(10.0)


def test_roofline_memory_bound():
    # Tiny compute, huge traffic: memory time dominates.
    spec = KernelSpec("memory-heavy", flops=10**6, bytes_moved=10**12)
    assert roofline_time_ms(spec, peak_tflops=100, bandwidth_gbs=1000) == pytest.approx(1000.0)


def test_roofline_bad_hardware_rejected():
    spec = KernelSpec("k", flops=100, bytes_moved=100)
    with pytest.raises(ValueError):
        roofline_time_ms(spec, peak_tflops=0, bandwidth_gbs=100)


def test_arithmetic_intensity():
    spec = KernelSpec("k", flops=1000, bytes_moved=100)
    assert spec.arithmetic_intensity() == pytest.approx(10.0)


def test_attention_scores_rows_sum_to_one():
    q = [[1.0, 0.0], [0.0, 1.0]]
    k = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    scores = attention_scores(q, k)
    assert len(scores) == 2
    assert all(len(row) == 3 for row in scores)
    for row in scores:
        assert sum(row) == pytest.approx(1.0)
        assert all(0.0 < v < 1.0 for v in row)


def test_attention_scores_diagonal_dominates():
    q = [[1.0, 0.0], [0.0, 1.0]]
    k = [[1.0, 0.0], [0.0, 1.0]]
    scores = attention_scores(q, k)
    assert scores[0][0] > scores[0][1]
    assert scores[1][1] > scores[1][0]


def test_attention_scores_bad_shapes_rejected():
    with pytest.raises(ValueError):
        attention_scores([], [[1.0]])
    with pytest.raises(ValueError):
        attention_scores([[1.0, 2.0]], [[1.0]])
