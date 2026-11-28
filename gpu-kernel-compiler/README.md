# GPU Kernel Compiler

A tiny compiler that turns a small array-kernel DSL into OpenCL C, with the
optimizer passes a GPU compiler actually runs, and a virtual-GPU simulator
that checks the compiled kernel against a NumPy reference.

Built for the Intel GPU Compiler Software Engineer role (JR0289160): the JD
asks for compiler translations and optimizations targeting GPUs, performance
measurement and workload analysis, and hardware/software interaction. This
project is a hands-on, end-to-end version of that pipeline at small scale —
not a production compiler, and it does not claim LLVM or GPU-driver depth.

## The DSL

```text
kernel saxpy(a: f32[N], b: f32[N], s: f32) -> c: f32[N] {
    c[i] = a[i] * s + b[i];
}

kernel gemv(m: f32[N], v: f32[N], s: f32) -> r: f32[N] {
    let acc = 0;
    for j in 0..3 {
        acc = acc + m[i * 3 + j] * v[j];
    }
    r[i] = acc * s;
}
```

`i` is the implicit work-item index (one output element per work-item).
Statements: `let` bindings, indexed and scalar assignments, and
constant-bound `for` loops. Expressions: numbers, variables, indexed array
reads, `+ - * / %`, parentheses, unary minus.

## Pipeline

1. **Lexer** (`gpu_kernel_compiler/lexer.py`) — tokens, keywords, `->`, `..`.
2. **Parser** (`gpu_kernel_compiler/parser.py`) — recursive descent to a
   frozen-dataclass AST, with operator precedence.
3. **Optimizer** (`gpu_kernel_compiler/optimizer.py`) — constant folding,
   algebraic simplification (`x * 1` -> `x`, `x + 0` -> `x`), strength
   reduction (`x * 2` -> `x + x`), dead-code elimination of unused `let`
   bindings, and unrolling of constant-bound loops up to 8 iterations.
4. **Code generation** (`gpu_kernel_compiler/codegen.py`) — emits OpenCL C:
   `__kernel void saxpy(__global float* a, ...)`, `int i = get_global_id(0);`.
5. **Simulator** (`gpu_kernel_compiler/simulator.py`) — a virtual GPU grid:
   each work-item runs the kernel body; the result is compared against an
   independent NumPy reference so a wrong optimization shows up as a numeric
   mismatch.

## Run it

```bash
python3 run_demo.py            # prints both OpenCL kernels, verifies vs NumPy
python3 -m pytest tests/ -q    # 23 tests
```

Demo output (seeded): SAXPY N=1024 max abs error vs NumPy `0.0`; GEMV
256x3 max abs error vs NumPy `0.0` (float64 reference; the simulator uses
Python floats).

## What this is not

- No LLVM, no real GPU execution, no SPIR-V/PTX emission, no driver or
  hardware interaction. The OpenCL C is generated text, verified only by
  the simulator and by inspection — it has not been compiled by an OpenCL
  toolchain.
- The simulator is a scalar interpreter, not a performance model: it checks
  correctness, not speed. No benchmarks are claimed.
- Loop unrolling is capped at 8 iterations; larger loops are emitted as C
  `for` loops.
