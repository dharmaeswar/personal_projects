"""Deterministic legacy-to-modern Python transforms.

These are the reference migrations the evaluator benchmarks against. Each
transform is small, behaviour-preserving, and applied with the ``ast`` module
so it never rewrites code it cannot parse. They model the mechanical part of
an AI-assisted code migration (Python 2 idioms and pre-3.6 string formatting
moved to modern Python 3), leaving design decisions to the agent under test.
"""

from __future__ import annotations

import ast
import re

# ---------------------------------------------------------------------------
# Individual transforms (each returns the new source, or the input unchanged)
# ---------------------------------------------------------------------------

_PRINT_STMT = re.compile(r"^(\s*)print\s+([^(\s][^\n]*)$", re.MULTILINE)


def transform_print_statements(source: str) -> str:
    """``print x`` -> ``print(x)`` for simple top-level print statements."""
    def _repl(match: re.Match[str]) -> str:
        indent, expr = match.group(1), match.group(2).strip()
        return f"{indent}print({expr})"

    return _PRINT_STMT.sub(_repl, source)


def transform_xrange(source: str) -> str:
    """``xrange(...)`` -> ``range(...)``."""
    return re.sub(r"\bxrange\s*\(", "range(", source)


def transform_has_key(source: str) -> str:
    """``d.has_key(k)`` -> ``k in d``."""
    return re.sub(
        r"(\w[\w\.]*)\.has_key\(([^()]*)\)",
        lambda m: f"{m.group(2).strip()} in {m.group(1)}",
        source,
    )


_FORMAT_CALL = re.compile(
    r'"([^"]*)\{(\w+)\}([^"]*)"\.format\(\s*(\w+)\s*=\s*([^)]+)\)'
)


def transform_format_to_fstring(source: str) -> str:
    """``"{name}".format(name=value)`` -> ``f"{value}"`` (single placeholder)."""
    def _repl(match: re.Match[str]) -> str:
        pre, name, post, kwarg, value = match.groups()
        if name != kwarg:
            return match.group(0)
        return f'f"{pre}{{{value.strip()}}}{post}"'

    return _FORMAT_CALL.sub(_repl, source)


def transform_percent_format(source: str) -> str:
    """``"%s" % value`` -> ``"{}".format(value)`` (single %s placeholder)."""
    pattern = re.compile(r'"([^"]*)%s([^"]*)"\s*%\s*([\w\.]+(?:\([^)]*\))?)')

    def _repl(match: re.Match[str]) -> str:
        pre, post, value = match.groups()
        return f'"{pre}{{}}{post}".format({value})'

    return pattern.sub(_repl, source)


TRANSFORMS = (
    transform_print_statements,
    transform_xrange,
    transform_has_key,
    transform_format_to_fstring,
    transform_percent_format,
)


def apply_transforms(source: str, transforms=TRANSFORMS) -> tuple[str, list[str]]:
    """Apply each transform in order; return (new_source, names_applied)."""
    applied: list[str] = []
    current = source
    for fn in transforms:
        try:
            new = fn(current)
        except Exception:
            continue
        if new != current:
            applied.append(fn.__name__)
            current = new
    return current, applied


def migrate_source(source: str) -> str:
    """Migrate ``source`` with every deterministic transform.

    Raises ``SyntaxError`` if the input (or the result) does not parse, so a
    broken migration is never silently accepted as a reference.
    """
    ast.parse(source)
    migrated, _ = apply_transforms(source)
    ast.parse(migrated)
    return migrated
