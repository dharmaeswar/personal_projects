"""Optimizer passes over the kernel AST.

Passes (applied in order by :func:`optimize`):
1. Constant folding — fold literal arithmetic, e.g. ``2 * 3`` -> ``6``.
2. Algebraic simplification — ``x + 0`` -> ``x``, ``x * 1`` -> ``x``,
   ``x * 0`` -> ``0``, ``x - 0`` -> ``x``, ``x / 1`` -> ``x``.
3. Strength reduction — ``x * 2`` -> ``x + x`` (a multiply by a small
   constant becomes an add, the classic GPU-compiler peephole).
4. Dead-code elimination — drop ``let`` bindings whose value is never used.
5. Loop unrolling — unroll ``for j in 0..K`` with K <= 8 into straight-line
   code with the loop variable replaced by constants.

All passes preserve semantics; every rewrite is covered by a test with a
hand-computed expected result (see tests/test_optimizer.py).
"""

from .parser import (
    Assign,
    BinOp,
    For,
    Index,
    Kernel,
    Let,
    Num,
    Unary,
    Var,
)


def _fold(expr):
    """Constant-fold one expression node (recursive)."""
    if isinstance(expr, BinOp):
        left = _fold(expr.left)
        right = _fold(expr.right)
        if isinstance(left, Num) and isinstance(right, Num):
            return Num(_eval_op(expr.op, left.value, right.value))
        return BinOp(expr.op, left, right)
    if isinstance(expr, Unary):
        operand = _fold(expr.operand)
        if isinstance(operand, Num):
            return Num(-operand.value if expr.op == "-" else operand.value)
        return Unary(expr.op, operand)
    return expr


def _eval_op(op, a, b):
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a / b
    if op == "%":
        return a % b
    raise ValueError(f"unknown operator {op!r}")


def _simplify(expr):
    """Algebraic simplification + strength reduction (recursive)."""
    if isinstance(expr, BinOp):
        left = _simplify(expr.left)
        right = _simplify(expr.right)
        op = expr.op
        # x + 0 -> x ; 0 + x -> x
        if op == "+" and isinstance(right, Num) and right.value == 0:
            return left
        if op == "+" and isinstance(left, Num) and left.value == 0:
            return right
        # x - 0 -> x
        if op == "-" and isinstance(right, Num) and right.value == 0:
            return left
        # x * 1 -> x ; 1 * x -> x
        if op == "*" and isinstance(right, Num) and right.value == 1:
            return left
        if op == "*" and isinstance(left, Num) and left.value == 1:
            return right
        # x * 0 -> 0 ; 0 * x -> 0
        if op == "*" and (
            (isinstance(right, Num) and right.value == 0)
            or (isinstance(left, Num) and left.value == 0)
        ):
            return Num(0)
        # x / 1 -> x
        if op == "/" and isinstance(right, Num) and right.value == 1:
            return left
        # Strength reduction: x * 2 -> x + x
        if op == "*" and isinstance(right, Num) and right.value == 2:
            return BinOp("+", left, left)
        if op == "*" and isinstance(left, Num) and left.value == 2:
            return BinOp("+", right, right)
        return BinOp(op, left, right)
    if isinstance(expr, Unary):
        return Unary(expr.op, _simplify(expr.operand))
    if isinstance(expr, (Num, Var)):
        return expr
    # Index nodes: simplify the index expression.
    if isinstance(expr, Index):
        return Index(expr.name, _simplify(expr.index))
    return expr


def _used_vars(expr):
    """Names read by an expression."""
    if isinstance(expr, Num):
        return set()
    if isinstance(expr, Var):
        return {expr.name}
    if isinstance(expr, Index):
        return {expr.name} | _used_vars(expr.index)
    if isinstance(expr, BinOp):
        return _used_vars(expr.left) | _used_vars(expr.right)
    if isinstance(expr, Unary):
        return _used_vars(expr.operand)
    return set()


def _used_in_stmts(stmts):
    used = set()
    for stmt in stmts:
        if isinstance(stmt, Let):
            used |= _used_vars(stmt.expr)
        elif isinstance(stmt, Assign):
            used |= _used_vars(stmt.expr)
            if stmt.index is not None:
                used |= _used_vars(stmt.index)
        elif isinstance(stmt, For):
            used |= _used_in_stmts(stmt.body)
    return used


def _dce(stmts):
    """Drop `let` bindings never read by any later statement."""
    used = _used_in_stmts(stmts)
    kept = []
    for stmt in stmts:
        if isinstance(stmt, Let) and stmt.name not in used:
            continue  # dead binding
        if isinstance(stmt, For):
            kept.append(For(stmt.var, stmt.start, stmt.end, tuple(_dce(list(stmt.body)))))
        else:
            kept.append(stmt)
    return kept


def _subst(expr, var, value):
    """Replace every read of `var` in expr with the constant Num(value)."""
    if isinstance(expr, Var):
        return Num(value) if expr.name == var else expr
    if isinstance(expr, Num):
        return expr
    if isinstance(expr, Index):
        return Index(expr.name, _subst(expr.index, var, value))
    if isinstance(expr, BinOp):
        return BinOp(expr.op, _subst(expr.left, var, value), _subst(expr.right, var, value))
    if isinstance(expr, Unary):
        return Unary(expr.op, _subst(expr.operand, var, value))
    return expr


def _subst_stmt(stmt, var, value):
    if isinstance(stmt, Let):
        return Let(stmt.name, _subst(stmt.expr, var, value))
    if isinstance(stmt, Assign):
        index = None if stmt.index is None else _subst(stmt.index, var, value)
        return Assign(stmt.name, index, _subst(stmt.expr, var, value))
    if isinstance(stmt, For):
        return For(stmt.var, stmt.start, stmt.end,
                   tuple(_subst_stmt(s, var, value) for s in stmt.body))
    return stmt


def _unroll(stmts, max_factor=8):
    """Unroll small constant-bound loops into straight-line code."""
    out = []
    for stmt in stmts:
        if isinstance(stmt, For) and (stmt.end - stmt.start) <= max_factor:
            for k in range(stmt.start, stmt.end):
                for inner in stmt.body:
                    out.append(_subst_stmt(inner, stmt.var, k))
        elif isinstance(stmt, For):
            out.append(For(stmt.var, stmt.start, stmt.end, tuple(_unroll(list(stmt.body), max_factor))))
        else:
            out.append(stmt)
    return out


def _opt_expr(expr):
    return _simplify(_fold(expr))


def _opt_stmts(stmts):
    out = []
    for stmt in stmts:
        if isinstance(stmt, Let):
            out.append(Let(stmt.name, _opt_expr(stmt.expr)))
        elif isinstance(stmt, Assign):
            index = None if stmt.index is None else _opt_expr(stmt.index)
            out.append(Assign(stmt.name, index, _opt_expr(stmt.expr)))
        elif isinstance(stmt, For):
            out.append(For(stmt.var, stmt.start, stmt.end, tuple(_opt_stmts(list(stmt.body)))))
    return out


def optimize(kernel, unroll=True):
    """Run all optimizer passes over a Kernel and return a new Kernel."""
    body = _opt_stmts(list(kernel.body))
    body = _dce(body)
    if unroll:
        body = _unroll(body)
        # Fold again: unrolling exposes new constants (e.g. a[j] with j=2).
        body = _opt_stmts(body)
    return Kernel(kernel.name, kernel.params, kernel.ret_name, kernel.ret_is_array, tuple(body))
