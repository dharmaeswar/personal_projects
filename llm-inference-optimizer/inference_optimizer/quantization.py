"""Symmetric INT8 quantization with an accuracy-parity check.

Inference on an accelerator usually runs weights in INT8 or FP8 instead of
FP16. Quantization saves memory and bandwidth, but it changes the numbers,
so an enablement engineer checks the damage before shipping: quantize,
dequantize, and measure the error against a tolerance. If the error is
over tolerance, the model is not ready to serve in INT8.
"""

import math


def quantize_int8(values):
    """Symmetric per-tensor INT8 quantization.

    Returns (codes, scale) where codes are ints in [-127, 127] and
    ``value ~= code * scale``. An all-zero input maps to scale 1.0 so the
    round trip still returns zeros.
    """
    values = list(values)
    if not values:
        raise ValueError("cannot quantize an empty list")
    max_abs = max(abs(v) for v in values)
    scale = max_abs / 127.0 if max_abs > 0 else 1.0
    codes = [max(-127, min(127, round(v / scale))) for v in values]
    return codes, scale


def dequantize_int8(codes, scale):
    """Inverse of :func:`quantize_int8`."""
    return [c * scale for c in codes]


def quantize_rows_int8(matrix):
    """Per-row INT8 quantization of a matrix (list of rows).

    Per-row scales keep one large row from wrecking the precision of the
    rest. Returns (codes_matrix, scales).
    """
    codes = []
    scales = []
    for row in matrix:
        row_codes, row_scale = quantize_int8(row)
        codes.append(row_codes)
        scales.append(row_scale)
    return codes, scales


def dequantize_rows_int8(codes, scales):
    """Inverse of :func:`quantize_rows_int8`."""
    return [[c * s for c in row] for row, s in zip(codes, scales)]


def max_abs_error(original, reconstructed):
    """Largest absolute difference between two equal-length sequences."""
    if len(original) != len(reconstructed):
        raise ValueError("sequences must have the same length")
    return max((abs(a - b) for a, b in zip(original, reconstructed)), default=0.0)


def cosine_similarity(a, b):
    """Cosine similarity between two equal-length vectors."""
    if len(a) != len(b):
        raise ValueError("vectors must have the same length")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def accuracy_parity(original, reconstructed, tolerance):
    """True when the INT8 round trip stays within ``tolerance`` everywhere.

    Returns (passes, max_error, cosine) so a caller can log the numbers
    even when the check fails.
    """
    error = max_abs_error(original, reconstructed)
    return error <= tolerance, error, cosine_similarity(original, reconstructed)
