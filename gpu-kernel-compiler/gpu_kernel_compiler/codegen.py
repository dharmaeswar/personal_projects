"""OpenCL C code generation from the kernel AST.

Emits one ``__kernel`` function per DSL kernel: array parameters become
``__global`` pointers, scalars become plain values, and the implicit index
``i`` becomes ``get_global_id(0)``. Constant-bound ``for`` loops are emitted
as C loops; the optimizer can unroll them first (see optimizer.py).
"""

from .parser import Assign, BinOp, For, Index, Let, Num, Unary, Var


def _fmt_num(value):
    if isinstance(value, float):
        # Keep float literals valid C (2.0, not 2) and short.
        return repr(value) if "." in repr(value) else f"{value:.1f}"
    return str(value)


def gen_expr(expr):
    if isinstance(expr, Num):
        return _fmt_num(expr.value)
    if isinstance(expr, Var):
        return "i" if expr.name == "i" else expr.name
    if isinstance(expr, Index):
        return f"{expr.name}[{gen_expr(expr.index)}]"
    if isinstance(expr, BinOp):
        return f"({gen_expr(expr.left)} {expr.op} {gen_expr(expr.right)})"
    if isinstance(expr, Unary):
        return f"(-{gen_expr(expr.operand)})"
    raise ValueError(f"cannot generate code for {expr!r}")


def _gen_stmt(stmt, indent):
    pad = "    " * indent
    if isinstance(stmt, Let):
        return [f"{pad}float {stmt.name} = {gen_expr(stmt.expr)};"]
    if isinstance(stmt, Assign):
        if stmt.index is None:
            return [f"{pad}{stmt.name} = {gen_expr(stmt.expr)};"]
        return [f"{pad}{stmt.name}[{gen_expr(stmt.index)}] = {gen_expr(stmt.expr)};"]
    if isinstance(stmt, For):
        lines = [f"{pad}for (int {stmt.var} = {stmt.start}; {stmt.var} < {stmt.end}; {stmt.var}++) {{"]
        for inner in stmt.body:
            lines.extend(_gen_stmt(inner, indent + 1))
        lines.append(f"{pad}}}")
        return lines
    raise ValueError(f"cannot generate code for {stmt!r}")


def _param_decl(param):
    if param.is_array:
        return f"__global float* {param.name}"
    return f"float {param.name}"


def gen_kernel(kernel):
    """Return the OpenCL C source for one DSL kernel."""
    params = [_param_decl(p) for p in kernel.params]
    if kernel.ret_is_array:
        params.append(f"__global float* {kernel.ret_name}")
    else:
        params.append(f"float* {kernel.ret_name}")
    lines = [f"__kernel void {kernel.name}({', '.join(params)}) {{",
             "    int i = get_global_id(0);"]
    for stmt in kernel.body:
        lines.extend(_gen_stmt(stmt, 1))
    lines.append("}")
    return "\n".join(lines) + "\n"
