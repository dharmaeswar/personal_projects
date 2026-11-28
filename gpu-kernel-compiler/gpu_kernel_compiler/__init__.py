"""gpu-kernel-compiler: a tiny DSL-to-GPU-kernel compiler.

Pipeline: parse DSL source -> optimize (fold, simplify, strength-reduce,
dead-code-eliminate, unroll) -> generate OpenCL C -> simulate on a virtual
GPU grid to check the result against a reference.
"""

from .codegen import gen_kernel
from .optimizer import optimize
from .parser import parse
from .simulator import run_kernel

__all__ = ["compile_kernel", "parse", "optimize", "gen_kernel", "run_kernel"]


def compile_kernel(source, unroll=True):
    """Parse, optimize and generate OpenCL C for one DSL kernel.

    Returns ``(kernel_ast, opencl_source)``.
    """
    kernel = parse(source)
    kernel = optimize(kernel, unroll=unroll)
    return kernel, gen_kernel(kernel)
