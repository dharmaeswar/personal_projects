"""Build-metadata and lint checks for a Python package.

Checks that mirror what a language-ecosystem / build-tools team looks
for before a package ships: packaging metadata, a README, a test
layout, and hygiene issues inside the source (missing ``__init__``,
unused imports, wildcard imports).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

METADATA_FILES = ("pyproject.toml", "setup.py", "setup.cfg")


@dataclass
class CheckResult:
    code: str
    level: str  # "error" | "warning" | "ok"
    message: str
    path: str = ""


def _check_metadata(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    found = [f for f in METADATA_FILES if (root / f).exists()]
    if not found:
        results.append(CheckResult("PKG001", "error", "no packaging metadata found (need pyproject.toml or setup.py)", ""))
    else:
        results.append(CheckResult("PKG001", "ok", f"packaging metadata present: {', '.join(found)}", ""))
    if (root / "README.md").exists() or (root / "README.rst").exists():
        results.append(CheckResult("PKG002", "ok", "README present", ""))
    else:
        results.append(CheckResult("PKG002", "warning", "no README.md found", ""))
    if (root / "pyproject.toml").exists():
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        if re.search(r"(?m)^name\s*=", text):
            results.append(CheckResult("PKG003", "ok", "pyproject.toml declares a project name", "pyproject.toml"))
        else:
            results.append(CheckResult("PKG003", "warning", "pyproject.toml has no project name", "pyproject.toml"))
    return results


def _check_layout(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        rel = str(path.relative_to(root))
        if path.name != "__init__.py" and path.parent != root:
            # tests/ is not a package directory; pytest does not need __init__.py there.
            if path.parent.name in ("tests", "test"):
                continue
            init = path.parent / "__init__.py"
            if not init.exists():
                results.append(
                    CheckResult("PKG010", "error", "directory has .py files but no __init__.py", str(init.parent.relative_to(root)))
                )
                break
    else:
        results.append(CheckResult("PKG010", "ok", "every package directory has __init__.py", ""))
    tests = root / "tests"
    if tests.is_dir() and any(tests.rglob("test_*.py")):
        results.append(CheckResult("PKG011", "ok", "tests directory with test files present", "tests"))
    else:
        results.append(CheckResult("PKG011", "warning", "no tests/ directory with test_*.py files", "tests"))
    return results


def _check_source(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        rel = str(path.relative_to(root))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: dict[str, int] = {}
        used: set[str] = set()
        exported: set[str] = set()
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__all__"
                and isinstance(node.value, (ast.List, ast.Tuple))
            ):
                exported = {
                    e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
                }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported[alias.asname or alias.name.split(".")[0]] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue  # `from __future__ import annotations` is never "used" by name
                if any(a.name == "*" for a in node.names):
                    results.append(CheckResult("PKG020", "warning", "wildcard import", rel))
                for alias in node.names:
                    if alias.name != "*":
                        imported[alias.asname or alias.name] = node.lineno
            elif isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                pass
        # Names used as attribute roots (e.g. `os.path`) appear as Name nodes too.
        for name, line in sorted(imported.items()):
            if name not in used and name not in exported:
                results.append(
                    CheckResult("PKG021", "warning", f"unused import: {name} (line {line})", rel)
                )
    if not any(r.code in ("PKG020", "PKG021") for r in results):
        results.append(CheckResult("PKG020", "ok", "no wildcard imports or unused imports found", ""))
    return results


def run_checks(package_dir: str | Path) -> list[CheckResult]:
    """Run all build-metadata / lint checks on the package."""
    root = Path(package_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {package_dir}")
    return _check_metadata(root) + _check_layout(root) + _check_source(root)
