"""Code-generation tests: the emitted OpenCL C for SAXPY and GEMV."""

from gpu_kernel_compiler import compile_kernel

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


def test_saxpy_opencl():
    _, src = compile_kernel(SAXPY)
    assert "__kernel void saxpy(__global float* a, __global float* b, float s, __global float* c)" in src
    assert "int i = get_global_id(0);" in src
    assert "c[i] = ((a[i] * s) + b[i]);" in src


def test_gemv_opencl_unrolled():
    _, src = compile_kernel(GEMV)
    # The 0..3 loop is unrolled: no for-loop remains, three accumulation lines.
    assert "for (int j" not in src
    assert "float acc = 0;" in src
    assert "acc = (acc + (m[(i * 3)] * v[0]));" in src
    assert "r[i] = (acc * s);" in src


def test_gemv_opencl_no_unroll():
    _, src = compile_kernel(GEMV, unroll=False)
    assert "for (int j = 0; j < 3; j++) {" in src
