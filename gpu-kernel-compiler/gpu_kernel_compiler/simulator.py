"""Virtual-GPU simulator: execute a kernel AST over a grid of work-items.

This is the "hardware model" half of the compiler: each work-item ``i`` runs
the kernel body with its own index, exactly like one OpenCL work-item. Array
arguments are Python lists of floats; scalars are plain numbers. The
simulator is the correctness oracle for the project: the demo and the tests
run a compiled kernel here and compare the result against an independent
NumPy reference, so a wrong optimization or code-generation bug shows up as
a numeric mismatch instead of a silent pass.
"""

from .parser import Assign, BinOp, For, Index, Let, Num, Unary, Var


def _eval(expr, env, arrays, i):
    if isinstance(expr, Num):
        return float(expr.value)
    if isinstance(expr, Var):
        if expr.name == "i":
            return float(i)
        return env[expr.name]
    if isinstance(expr, Index):
        idx = int(_eval(expr.index, env, arrays, i))
        return arrays[expr.name][idx]
    if isinstance(expr, BinOp):
        left = _eval(expr.left, env, arrays, i)
        right = _eval(expr.right, env, arrays, i)
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        if expr.op == "*":
            return left * right
        if expr.op == "/":
            return left / right
        if expr.op == "%":
            return left % right
        raise ValueError(f"unknown operator {expr.op!r}")
    if isinstance(expr, Unary):
        return -_eval(expr.operand, env, arrays, i)
    raise ValueError(f"cannot evaluate {expr!r}")


def _exec_stmts(stmts, env, arrays, i):
    for stmt in stmts:
        if isinstance(stmt, Let):
            env[stmt.name] = _eval(stmt.expr, env, arrays, i)
        elif isinstance(stmt, Assign):
            if stmt.index is None:
                env[stmt.name] = _eval(stmt.expr, env, arrays, i)
            else:
                idx = int(_eval(stmt.index, env, arrays, i))
                arrays[stmt.name][idx] = _eval(stmt.expr, env, arrays, i)
        elif isinstance(stmt, For):
            for k in range(stmt.start, stmt.end):
                env[stmt.var] = float(k)
                _exec_stmts(list(stmt.body), env, arrays, i)
        else:
            raise ValueError(f"cannot execute {stmt!r}")


def run_kernel(kernel, n, **args):
    """Execute `kernel` for work-items 0..n-1.

    Array arguments are lists (copied, so the caller's data is untouched);
    scalar arguments are numbers. Returns the output array as a list of
    floats, named by the kernel's return parameter.
    """
    arrays = {}
    env = {}
    for param in kernel.params:
        value = args[param.name]
        if param.is_array:
            arrays[param.name] = [float(v) for v in value]
        else:
            env[param.name] = float(value)
    out = [0.0] * n
    arrays[kernel.ret_name] = out
    for i in range(n):
        _exec_stmts(list(kernel.body), dict(env), arrays, i)
    return out
