"""Simulator tests: virtual-GPU execution against hand-computed values."""

import numpy as np

from gpu_kernel_compiler import compile_kernel, parse, run_kernel

SAXPY = """kernel saxpy(a: f32[N], b: f32[N], s: f32) -> c: f32[N] {
    c[i] = a[i] * s + b[i];
}"""

GEMV = """kernel gemv(m: f32[N], v: f32[N], s: f32) -> r: f32[N] {
    let acc = 0;
    for j in 0..3 {
        acc = acc + m[i * 3 + j] * v[j];
    }
    r[i] = acc * s;
}"""


def test_saxpy_hand_computed():
    # a=[1,2,3,4], b=[10,20,30,40], s=2 -> 1*2+10=12, 2*2+20=24, 3*2+30=36, 4*2+40=48
    k, _ = compile_kernel(SAXPY)
    out = run_kernel(k, 4, a=[1, 2, 3, 4], b=[10, 20, 30, 40], s=2)
    assert out == [12.0, 24.0, 36.0, 48.0]


def test_saxpy_matches_numpy():
    rng = np.random.default_rng(7)
    a = rng.normal(size=64)
    b = rng.normal(size=64)
    s = 2.5
    k, _ = compile_kernel(SAXPY)
    out = run_kernel(k, 64, a=a.tolist(), b=b.tolist(), s=s)
    np.testing.assert_allclose(out, a * s + b, rtol=0, atol=1e-12)


def test_gemv_hand_computed():
    # Rows: [1,2,3] and [4,5,6]; v=[10,20,30]; s=2.
    # Row 0: (1*10 + 2*20 + 3*30) * 2 = 140 * 2 = 280
    # Row 1: (4*10 + 5*20 + 6*30) * 2 = 320 * 2 = 640
    k, _ = compile_kernel(GEMV)
    out = run_kernel(k, 2, m=[1, 2, 3, 4, 5, 6], v=[10, 20, 30], s=2)
    assert out == [280.0, 640.0]


def test_gemv_matches_numpy():
    rng = np.random.default_rng(11)
    m = rng.normal(size=(5, 3))
    v = rng.normal(size=3)
    s = 1.5
    k, _ = compile_kernel(GEMV)
    out = run_kernel(k, 5, m=m.reshape(-1).tolist(), v=v.tolist(), s=s)
    np.testing.assert_allclose(out, (m @ v) * s, rtol=0, atol=1e-12)


def test_optimized_and_unoptimized_agree():
    # The optimizer must not change results: same kernel, both pipelines.
    rng = np.random.default_rng(3)
    a = rng.normal(size=32)
    b = rng.normal(size=32)
    opt, _ = compile_kernel(SAXPY, unroll=True)
    plain = parse(SAXPY)
    out_opt = run_kernel(opt, 32, a=a.tolist(), b=b.tolist(), s=3.0)
    out_plain = run_kernel(plain, 32, a=a.tolist(), b=b.tolist(), s=3.0)
    assert out_opt == out_plain


def test_input_arrays_not_mutated():
    k, _ = compile_kernel(SAXPY)
    a = [1.0, 2.0]
    b = [3.0, 4.0]
    run_kernel(k, 2, a=a, b=b, s=2)
    assert a == [1.0, 2.0] and b == [3.0, 4.0]
