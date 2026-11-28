"""Numerical-rules lint: static checks that keep floats out of money code.

The methodology rule — no floating-point types for money or IRR
solves — is only worth anything if it is enforced mechanically, the
way a lint rule enforces a style rule. This module is that check:
it parses the decimal calculation modules with ``ast`` and reports

- float literals (``0.1`` is not exactly 0.1, so a float literal in a
  money module is a defect even before it is used),
- calls to ``float(...)`` (a conversion is how a float enters),
- ``import math`` / ``from math import ...`` (math functions return
  floats; the decimal modules must not use them).

``isinstance(value, float)`` — the type test ``money()`` uses to
REJECT floats — is not a violation: it is a name reference, not a
literal and not a call. Docstrings and comments are not code and are
never flagged.

``check_source`` works on source text so the test suite can prove
the checker catches planted violations; ``check_module`` checks a
file by path; ``lint_decimal_modules`` checks every module in
DECIMAL_MODULES and returns all violations as (module, line, rule)
tuples. An empty list means the rule holds.
"""

import ast
import os

DECIMAL_MODULES = (
    "decimal_solver.py",
    "decimal_measures.py",
    "pme.py",
    "multiples.py",
    "pooled.py",
    "conformance.py",
)


def check_source(source, module="<source>"):
    """Return [(module, line, rule)] violations found in source text."""
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            violations.append(
                (module, node.lineno, "float literal %r" % (node.value,)))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "float":
            violations.append((module, node.lineno, "float() call"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "math" or alias.name.startswith("math."):
                    violations.append(
                        (module, node.lineno, "import of math module"))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "math" or (
                    node.module or "").startswith("math."):
                violations.append(
                    (module, node.lineno, "import from math module"))
    return violations


def check_module(path):
    """Return violations for one file, labelled by its basename."""
    with open(path, "r", encoding="utf-8") as handle:
        return check_source(handle.read(), module=os.path.basename(path))


def lint_decimal_modules(package_dir=None):
    """Check every decimal module in the perf package directory."""
    if package_dir is None:
        package_dir = os.path.dirname(os.path.abspath(__file__))
    violations = []
    for name in DECIMAL_MODULES:
        violations.extend(check_module(os.path.join(package_dir, name)))
    return violations
