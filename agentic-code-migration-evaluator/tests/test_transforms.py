"""Tests for the deterministic legacy -> modern transforms."""

import pytest

from migration_evaluator.transforms import (
    apply_transforms,
    migrate_source,
    transform_format_to_fstring,
    transform_has_key,
    transform_percent_format,
    transform_print_statements,
    transform_xrange,
)


def test_print_statement_becomes_call():
    assert transform_print_statements('print "hello"\n') == 'print("hello")\n'


def test_print_call_left_alone():
    source = 'print("hello")\n'
    assert transform_print_statements(source) == source


def test_xrange_becomes_range():
    assert transform_xrange("for i in xrange(5):\n    pass\n") == (
        "for i in range(5):\n    pass\n"
    )


def test_has_key_becomes_in():
    assert transform_has_key("if d.has_key(k):\n    pass\n") == (
        "if k in d:\n    pass\n"
    )


def test_format_call_becomes_fstring():
    assert (
        transform_format_to_fstring('"{name}".format(name=value)')
        == 'f"{value}"'
    )


def test_percent_format_becomes_format_call():
    assert (
        transform_percent_format('return "%s!" % name')
        == 'return "{}!".format(name)'
    )


def test_apply_transforms_reports_names_applied():
    _, applied = apply_transforms("for i in xrange(3):\n    print i\n")
    assert "transform_xrange" in applied
    assert "transform_print_statements" in applied


def test_migrate_source_rejects_unparseable_input():
    with pytest.raises(SyntaxError):
        migrate_source("def broken(:\n")


def test_migrate_source_output_parses():
    source = "def f(n):\n    return [i for i in xrange(n)]\n"
    compile(migrate_source(source), "<test>", "exec")
