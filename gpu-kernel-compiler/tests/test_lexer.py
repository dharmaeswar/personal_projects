"""Lexer tests: token kinds, values, and error on bad characters."""

import pytest

from gpu_kernel_compiler.lexer import LexError, tokenize


def test_saxpy_tokens():
    tokens = tokenize("kernel saxpy(a: f32[N], s: f32) -> c: f32[N] { }")
    kinds = [(t.kind, t.value) for t in tokens]
    assert kinds[0] == ("keyword", "kernel")
    assert kinds[1] == ("ident", "saxpy")
    assert kinds[2] == ("sym", "(")
    assert ("keyword", "f32") in kinds
    assert ("sym", "->") in kinds
    assert kinds[-1] == ("sym", "}")


def test_numbers():
    tokens = tokenize("2 3.5 0")
    assert [t.value for t in tokens] == [2, 3.5, 0]
    assert [type(t.value).__name__ for t in tokens] == ["int", "float", "int"]


def test_range_operator():
    tokens = tokenize("for j in 0..3 { }")
    assert ("sym", "..") in [(t.kind, t.value) for t in tokens]


def test_bad_character():
    with pytest.raises(LexError):
        tokenize("kernel x(a: f32) -> c: f32 { c[i] = a[i] @ 2; }")
