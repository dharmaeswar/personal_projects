"""Tests for the numerical-rules lint (perf/numerical_rules.py).

Two directions: the decimal modules in the package must be clean,
and the checker itself must catch planted violations — a lint that
cannot fail is not a lint.
"""

from perf.numerical_rules import check_source, lint_decimal_modules


def test_decimal_modules_have_no_float_violations():
    assert lint_decimal_modules() == []


def test_checker_catches_float_literal():
    violations = check_source("x = 0.1\n")
    assert len(violations) == 1
    assert "float literal" in violations[0][2]


def test_checker_catches_float_call():
    violations = check_source("x = float('1.5')\n")
    assert len(violations) == 1
    assert violations[0][2] == "float() call"


def test_checker_catches_math_import():
    assert check_source("import math\n") != []
    assert check_source("from math import sqrt\n") != []


def test_checker_allows_isinstance_float_rejection():
    # money() rejects floats via isinstance(value, float): a name
    # reference used to keep floats OUT, not a violation.
    assert check_source("ok = isinstance(value, float)\n") == []


def test_checker_ignores_docstrings_and_comments():
    source = '"""Rates like 0.1 are inexact."""\n# 0.25 in a comment\nx = 1\n'
    assert check_source(source) == []
