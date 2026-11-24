"""Tests for scoring-execution optimization (chunked / benchmarked scoring)."""

import numpy as np
import pandas as pd
import pytest

from ccar_validation.data import generate_portfolio, train_test_split
from ccar_validation.models import fit_all
from ccar_validation.optimize import (
    benchmark_scoring,
    build_optimization_section,
    score_in_chunks,
    score_rowwise,
)


@pytest.fixture(scope="module")
def fitted():
    portfolio = generate_portfolio()
    train, test = train_test_split(portfolio)
    return fit_all(train), train, test


def test_chunked_scores_match_batch(fitted):
    models, _, test = fitted
    batch = np.asarray(models["champion"].predict(test), dtype=float)
    for size in (1, 7, 250, 500, 1000, len(test), len(test) + 10):
        chunked = score_in_chunks(models["champion"], test, size)
        assert len(chunked) == len(test)
        assert np.allclose(chunked, batch, atol=1e-12)


def test_rowwise_scores_match_batch(fitted):
    models, _, test = fitted
    batch = np.asarray(models["champion"].predict(test), dtype=float)
    rowwise = score_rowwise(models["champion"], test)
    assert len(rowwise) == len(test)
    assert np.allclose(rowwise, batch, atol=1e-12)


def test_chunk_size_must_be_positive(fitted):
    models, _, test = fitted
    with pytest.raises(ValueError):
        score_in_chunks(models["champion"], test, 0)
    with pytest.raises(ValueError):
        score_in_chunks(models["champion"], test, -5)


def test_empty_frame_scores_empty(fitted):
    models, _, test = fitted
    empty = test.iloc[0:0]
    assert score_in_chunks(models["champion"], empty, 100).shape == (0,)


def test_benchmark_reports_positive_throughput_and_best_chunk(fitted):
    models, _, test = fitted
    bench = benchmark_scoring(models["champion"], test, chunk_sizes=(250, 500, 1000))
    assert bench.rows == len(test)
    assert bench.rowwise_rows_per_sec > 0
    assert bench.batch_rows_per_sec > 0
    assert bench.best_chunk_size in (250, 500, 1000)
    assert bench.best_chunk_rows_per_sec > 0
    assert bench.chunk_scores_match_batch is True


def test_benchmark_chunked_faster_than_rowwise(fitted):
    models, _, test = fitted
    bench = benchmark_scoring(models["champion"], test, chunk_sizes=(500,))
    # Vectorized execution must beat one model call per loan by a wide margin.
    assert bench.speedup_vs_rowwise > 5.0


def test_optimization_section_text(fitted):
    models, _, test = fitted
    bench = benchmark_scoring(models["champion"], test, chunk_sizes=(500,))
    section = build_optimization_section(bench)
    assert "SCORING EXECUTION OPTIMIZATION" in section
    assert "Best chunk size: 500" in section
    assert "Chunked scores match batch scores: yes" in section
    assert "rows/sec" in section
