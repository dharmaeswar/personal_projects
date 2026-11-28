"""Parser tests: AST shape for SAXPY and GEMV kernels, and error handling."""

import pytest

from gpu_kernel_compiler.parser import (
    Assign,
    BinOp,
    For,
    Index,
    Let,
    Num,
    Var,
    parse,
    ParseError,
)

SAXPY = """kernel saxpy(a: f32[N], b: f32[N], s: f32) -> c: f32[N] {
    c[i] = a[i] * s + b[i];
}"""


def test_saxpy_ast():
    k = parse(SAXPY)
    assert k.name == "saxpy"
    assert [p.name for p in k.params] == ["a", "b", "s"]
    assert [p.is_array for p in k.params] == [True, True, False]
    assert k.ret_name == "c" and k.ret_is_array is True
    assert len(k.body) == 1
    stmt = k.body[0]
    assert isinstance(stmt, Assign)
    assert stmt.name == "c"
    assert stmt.index == Var("i")
    # c[i] = (a[i] * s) + b[i]
    assert isinstance(stmt.expr, BinOp) and stmt.expr.op == "+"
    assert stmt.expr.left == BinOp("*", Index("a", Var("i")), Var("s"))
    assert stmt.expr.right == Index("b", Var("i"))


def test_for_loop_and_let():
    src = """kernel gemv(m: f32[N], v: f32[N], s: f32) -> r: f32[N] {
        let acc = 0;
        for j in 0..3 {
            acc = acc + m[i * 3 + j] * v[j];
        }
        r[i] = acc * s;
    }"""
    k = parse(src)
    assert isinstance(k.body[0], Let)
    assert k.body[0].name == "acc" and k.body[0].expr == Num(0)
    loop = k.body[1]
    assert isinstance(loop, For)
    assert (loop.var, loop.start, loop.end) == ("j", 0, 3)
    assert len(loop.body) == 1
    assert isinstance(k.body[2], Assign)


def test_operator_precedence():
    k = parse("kernel t(a: f32[N]) -> c: f32[N] { c[i] = a[i] + 2 * 3; }")
    # 2 * 3 binds tighter than +
    assert k.body[0].expr.right == BinOp("*", Num(2), Num(3))


def test_parse_errors():
    with pytest.raises(ParseError):
        parse("kernel saxpy(a: f32[N]) -> c: f32[N] { c[i] = a[i] }")  # missing ;
    with pytest.raises(ParseError):
        parse("kernel saxpy(a: f32[N]) -> c: f32[N] { c[i] = a[i] * ; }")
    with pytest.raises(ParseError):
        parse("not a kernel at all")
