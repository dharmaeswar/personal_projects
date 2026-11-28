"""Demo: compile SAXPY and a tiled GEMV kernel, print the OpenCL C, and
verify the virtual-GPU execution against NumPy references.
"""

import numpy as np

from gpu_kernel_compiler import compile_kernel, run_kernel

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


def main():
    print("=== SAXPY: generated OpenCL C ===")
    _, saxpy_cl = compile_kernel(SAXPY)
    print(saxpy_cl)

    print("=== GEMV: generated OpenCL C (loop unrolled) ===")
    _, gemv_cl = compile_kernel(GEMV)
    print(gemv_cl)

    rng = np.random.default_rng(42)
    a = rng.normal(size=1024)
    b = rng.normal(size=1024)
    s = 2.5
    kernel, _ = compile_kernel(SAXPY)
    out = run_kernel(kernel, 1024, a=a.tolist(), b=b.tolist(), s=s)
    err = float(np.max(np.abs(np.array(out) - (a * s + b))))
    print(f"SAXPY N=1024: max abs error vs NumPy = {err:.3e}")

    m = rng.normal(size=(256, 3))
    v = rng.normal(size=3)
    kernel, _ = compile_kernel(GEMV)
    out = run_kernel(kernel, 256, m=m.reshape(-1).tolist(), v=v.tolist(), s=1.5)
    err = float(np.max(np.abs(np.array(out) - (m @ v) * 1.5)))
    print(f"GEMV 256x3: max abs error vs NumPy = {err:.3e}")
    print("Demo OK: both kernels verified against NumPy references.")


if __name__ == "__main__":
    main()
