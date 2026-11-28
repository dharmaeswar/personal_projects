"""Optimizer tests. Every expected value below is hand-computed."""

from gpu_kernel_compiler.optimizer import optimize
from gpu_kernel_compiler.parser import BinOp, Index, Num, Var, parse


def _body(source, unroll=True):
    return optimize(parse(source), unroll=unroll).body


def test_constant_folding():
    # 2 * 3 + x folds the literal part to 6; x stays symbolic.
    stmts = _body("kernel t(a: f32[N]) -> c: f32[N] { c[i] = 2 * 3 + a[i]; }")
    assert stmts[0].expr.left == Num(6)
    assert stmts[0].expr.right == Index("a", Var("i"))


def test_algebraic_simplification():
    stmts = _body(
        "kernel t(a: f32[N], b: f32[N]) -> c: f32[N] { "
        "c[i] = a[i] * 1 + b[i] + 0; }",
        unroll=False,
    )
    # a[i] * 1 -> a[i]; ... + 0 -> dropped
    assert stmts[0].expr == BinOp("+", Index("a", Var("i")), Index("b", Var("i")))


def test_strength_reduction():
    stmts = _body(
        "kernel t(a: f32[N]) -> c: f32[N] { c[i] = a[i] * 2; }",
        unroll=False,
    )
    # x * 2 -> x + x
    assert stmts[0].expr == BinOp("+", Index("a", Var("i")), Index("a", Var("i")))


def test_dead_code_elimination():
    stmts = _body(
        "kernel t(a: f32[N]) -> c: f32[N] { "
        "let dead = a[i] * 5; let live = 2; c[i] = a[i] + live; }",
        unroll=False,
    )
    names = [s.name for s in stmts if hasattr(s, "name")]
    assert "dead" not in names
    assert "live" in names


def test_loop_unrolling():
    stmts = _body(
        "kernel t(m: f32[N], v: f32[N]) -> r: f32[N] { "
        "let acc = 0; "
        "for j in 0..3 { acc = acc + m[i * 3 + j] * v[j]; } "
        "r[i] = acc; }",
    )
    # let acc, 3 unrolled accumulation assigns, final store = 5 statements.
    assert len(stmts) == 5
    # First unrolled step uses j = 0: m[i*3] * v[0]; last uses j = 2.
    first = stmts[1]
    assert first.expr.right == BinOp("*", Index("m", BinOp("*", Var("i"), Num(3))),
                                     Index("v", Num(0)))
    last = stmts[3]
    assert last.expr.right == BinOp("*", Index("m", BinOp("+", BinOp("*", Var("i"), Num(3)), Num(2))),
                                    Index("v", Num(2)))


def test_large_loop_not_unrolled():
    stmts = _body(
        "kernel t(a: f32[N]) -> c: f32[N] { "
        "for j in 0..64 { c[i] = c[i] + a[j]; } }",
    )
    assert len(stmts) == 1  # loop kept intact: 64 iterations is over the cap
