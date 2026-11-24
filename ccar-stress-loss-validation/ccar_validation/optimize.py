"""Scoring-execution optimization for the deployed stress-loss models.

Covers the "optimize" half of the deployment & platform side of a
credit-risk modelling team: how the champion loss forecaster is executed
at scale. Compares naive per-loan (row-wise) scoring with vectorized
batch scoring and chunked scoring, measures rows/second for each, and
picks the chunk size that scores fastest — without changing any score.

Chunked scoring matters when the portfolio is far bigger than memory for
one batch: it keeps peak memory bounded while staying close to batch
speed. Every chunked run is checked against the single-batch result, so
an optimization can never silently change a forecast.

All data is synthetic and seeded; nothing here is a real filing or a claim
about any real institution's models.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ScoringBenchmark:
    """Measured scoring throughput for one model on one dataset."""

    rows: int
    rowwise_rows_per_sec: float
    batch_rows_per_sec: float
    chunk_results: dict[int, float] = field(default_factory=dict)  # chunk size -> rows/sec
    chunk_scores_match_batch: bool = False

    @property
    def best_chunk_size(self) -> int | None:
        if not self.chunk_results:
            return None
        return max(self.chunk_results, key=lambda size: self.chunk_results[size])

    @property
    def best_chunk_rows_per_sec(self) -> float:
        size = self.best_chunk_size
        return self.chunk_results[size] if size is not None else 0.0

    @property
    def speedup_vs_rowwise(self) -> float:
        """How many times faster the best chunked run is than row-wise scoring."""
        if self.rowwise_rows_per_sec <= 0:
            return 0.0
        return self.best_chunk_rows_per_sec / self.rowwise_rows_per_sec


def score_rowwise(model, df: pd.DataFrame) -> np.ndarray:
    """Naive per-loan scoring: one model call per row.

    This is the unoptimized baseline — the execution pattern a pipeline
    inherits when scoring is written loan-by-loan. Kept only so the
    benchmark can measure what optimization actually buys.
    """
    scores = [float(model.predict(df.iloc[[i]])[0]) for i in range(len(df))]
    return np.asarray(scores, dtype=float)


def score_in_chunks(model, df: pd.DataFrame, chunk_size: int) -> np.ndarray:
    """Score the portfolio in fixed-size chunks and concatenate the results.

    Keeps peak memory bounded for portfolios too large to score in one
    batch, while staying close to batch speed. Chunk size must be a
    positive integer; an empty frame returns an empty array.
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")
    if len(df) == 0:
        return np.empty(0, dtype=float)
    parts = [
        np.asarray(model.predict(df.iloc[start:start + chunk_size]), dtype=float)
        for start in range(0, len(df), chunk_size)
    ]
    return np.concatenate(parts)


def benchmark_scoring(model, df: pd.DataFrame,
                      chunk_sizes: tuple[int, ...] = (250, 500, 1000)) -> ScoringBenchmark:
    """Time row-wise, single-batch, and chunked scoring on the same data.

    Chunked scores must match the single-batch scores exactly (within
    1e-12); a mismatch means the optimization changed a forecast and the
    benchmark is reported as not matching.
    """
    t0 = time.perf_counter()
    rowwise = score_rowwise(model, df)
    rowwise_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    batch = np.asarray(model.predict(df), dtype=float)
    batch_seconds = time.perf_counter() - t0

    chunk_results: dict[int, float] = {}
    match = True
    for size in chunk_sizes:
        t0 = time.perf_counter()
        chunked = score_in_chunks(model, df, size)
        seconds = time.perf_counter() - t0
        chunk_results[size] = len(df) / seconds if seconds > 0 else 0.0
        if not np.allclose(chunked, batch, atol=1e-12):
            match = False

    return ScoringBenchmark(
        rows=len(df),
        rowwise_rows_per_sec=len(df) / rowwise_seconds if rowwise_seconds > 0 else 0.0,
        batch_rows_per_sec=len(df) / batch_seconds if batch_seconds > 0 else 0.0,
        chunk_results=chunk_results,
        chunk_scores_match_batch=match and np.allclose(rowwise, batch, atol=1e-12),
    )


def build_optimization_section(benchmark: ScoringBenchmark) -> str:
    """Plain-text report section for the scoring-optimization benchmark."""
    lines = []
    lines.append("11. SCORING EXECUTION OPTIMIZATION")
    lines.append(f"   Rows scored: {benchmark.rows}")
    lines.append(f"   Row-wise scoring:  {benchmark.rowwise_rows_per_sec:10.1f} rows/sec (unoptimized baseline)")
    lines.append(f"   Single batch:      {benchmark.batch_rows_per_sec:10.1f} rows/sec")
    for size in sorted(benchmark.chunk_results):
        lines.append(f"   Chunk size {size:5d}:   {benchmark.chunk_results[size]:10.1f} rows/sec")
    lines.append(f"   Best chunk size: {benchmark.best_chunk_size} "
                 f"({benchmark.best_chunk_rows_per_sec:.1f} rows/sec, "
                 f"{benchmark.speedup_vs_rowwise:.1f}x vs row-wise)")
    lines.append(f"   Chunked scores match batch scores: "
                 f"{'yes' if benchmark.chunk_scores_match_batch else 'NO - OPTIMIZATION CHANGED SCORES'}")
    return "\n".join(lines)
