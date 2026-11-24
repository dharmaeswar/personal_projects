"""Kernel cost models: tiled matmul and a roofline check.

High-performance kernels are where inference speed actually comes from:
a matmul that reuses data in cache (tiling) beats a naive triple loop, and
a roofline model says whether a kernel is limited by compute or by memory
bandwidth before anyone writes the kernel. The matmuls here are small
pure-Python reference implementations — they exist to prove the tiled
layout computes the same result as the naive one, and to measure the
operation counts the roofline needs.
"""

import math
from dataclasses import dataclass


def matmul_naive(a, b):
    """Plain triple-loop matrix product. ``a`` is m x k, ``b`` is k x n."""
    m = len(a)
    k = len(a[0]) if m else 0
    n = len(b[0]) if b else 0
    if any(len(row) != k for row in a) or any(len(row) != n for row in b):
        raise ValueError("ragged or mismatched matrices")
    out = [[0.0] * n for _ in range(m)]
    for i in range(m):
        for j in range(n):
            total = 0.0
            for p in range(k):
                total += a[i][p] * b[p][j]
            out[i][j] = total
    return out


def matmul_tiled(a, b, tile=8):
    """Cache-blocked matrix product: same result as :func:`matmul_naive`.

    The inner loops work on ``tile`` x ``tile`` blocks so each block of
    ``a`` and ``b`` is loaded once per block row/column instead of once
    per output element.
    """
    if tile <= 0:
        raise ValueError("tile must be positive")
    m = len(a)
    k = len(a[0]) if m else 0
    n = len(b[0]) if b else 0
    if any(len(row) != k for row in a) or any(len(row) != n for row in b):
        raise ValueError("ragged or mismatched matrices")
    out = [[0.0] * n for _ in range(m)]
    for ii in range(0, m, tile):
        for jj in range(0, n, tile):
            for pp in range(0, k, tile):
                for i in range(ii, min(ii + tile, m)):
                    for j in range(jj, min(jj + tile, n)):
                        total = out[i][j]
                        for p in range(pp, min(pp + tile, k)):
                            total += a[i][p] * b[p][j]
                        out[i][j] = total
    return out


def matmul_flops(m: int, n: int, k: int) -> int:
    """FLOPs for an m x k by k x n product (one multiply-add = 2 FLOPs)."""
    return 2 * m * n * k


def matmul_bytes(m: int, n: int, k: int, dtype_bytes: int = 2) -> int:
    """Bytes moved by a matmul that reads both inputs once and writes the output."""
    return (m * k + k * n + m * n) * dtype_bytes


@dataclass(frozen=True)
class KernelSpec:
    """A kernel described by its work and its memory traffic."""

    name: str
    flops: int
    bytes_moved: int

    def arithmetic_intensity(self) -> float:
        """FLOPs per byte — above the ridge point means compute-bound."""
        if self.bytes_moved == 0:
            return math.inf
        return self.flops / self.bytes_moved


def roofline_time_ms(spec: KernelSpec, peak_tflops: float, bandwidth_gbs: float) -> float:
    """Lower-bound runtime in milliseconds from the roofline model.

    The kernel cannot run faster than its compute time (FLOPs / peak) or
    its memory time (bytes / bandwidth); the slower of the two bounds it.
    """
    if peak_tflops <= 0 or bandwidth_gbs <= 0:
        raise ValueError("peak_tflops and bandwidth_gbs must be positive")
    compute_ms = spec.flops / (peak_tflops * 1e12) * 1000
    memory_ms = spec.bytes_moved / (bandwidth_gbs * 1e9) * 1000
    return max(compute_ms, memory_ms)


def attention_scores(query, key):
    """Scaled dot-product attention scores with a row softmax.

    ``query`` and ``key`` are lists of rows; returns the softmaxed score
    matrix. A reference for the fused-attention kernel shape: scores are
    Q K^T / sqrt(head_dim), then softmaxed per query row.
    """
    if not query or not key:
        raise ValueError("query and key must be non-empty")
    dim = len(query[0])
    if any(len(row) != dim for row in query) or any(len(row) != dim for row in key):
        raise ValueError("query and key rows must share one dimension")
    scale = 1.0 / math.sqrt(dim)
    scores = []
    for q in query:
        row = [sum(q[d] * k[d] for d in range(dim)) * scale for k in key]
        top = max(row)
        exps = [math.exp(x - top) for x in row]
        total = sum(exps)
        scores.append([e / total for e in exps])
    return scores
