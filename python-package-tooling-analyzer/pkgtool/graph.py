"""Import-graph construction for a Python package.

Walks a package directory, parses every ``.py`` file with ``ast``, and
records which module imports which other module inside the same package.
Relative imports are resolved to absolute dotted names. Imports of
stdlib / third-party modules are recorded separately as external edges.
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImportGraph:
    """Directed graph of intra-package imports."""

    root: Path
    package: str
    modules: set[str] = field(default_factory=set)
    edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    external: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def dependents(self, module: str) -> set[str]:
        """Modules that import ``module``."""
        return {src for src, dsts in self.edges.items() if module in dsts}

    def leaves(self) -> set[str]:
        """Modules that import nothing inside the package."""
        return {m for m in self.modules if not self.edges.get(m)}

    def roots(self) -> set[str]:
        """Modules nothing else inside the package imports."""
        imported = {d for dsts in self.edges.values() for d in dsts}
        return {m for m in self.modules if m not in imported}


def module_name(root: Path, path: Path) -> str:
    """Dotted module name of ``path`` relative to package ``root``."""
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_import(from_module: str, node: ast.ImportFrom) -> list[str]:
    """Resolve an ``ImportFrom`` node to absolute dotted module names."""
    level = node.level
    base_parts = from_module.split(".") if from_module else []
    if level > 0:
        # level 1 = current package, level 2 = parent, ...
        keep = max(len(base_parts) - level, 0)
        prefix = base_parts[:keep]
    else:
        prefix = []
    names: list[str] = []
    if node.module:
        names.append(".".join(prefix + node.module.split(".")))
    else:
        for alias in node.names:
            names.append(".".join(prefix + [alias.name]))
    return names


def _collect_imports(path: Path, mod: str) -> tuple[set[str], set[str]]:
    """Return (internal candidate imports, external imports) for one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    internal: set[str] = set()
    external: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                external.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for name in _resolve_import(mod, node):
                internal.add(name)
                # `from x import y` may import submodule x.y, not just names in x.
                for alias in node.names:
                    if alias.name != "*":
                        internal.add(f"{name}.{alias.name}")
    return internal, external


def build_graph(package_dir: str | os.PathLike) -> ImportGraph:
    """Build the import graph for the package at ``package_dir``."""
    root = Path(package_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {package_dir}")
    package = root.name
    graph = ImportGraph(root=root, package=package)
    py_files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    for path in py_files:
        mod = module_name(root, path)
        if not mod:
            continue
        graph.modules.add(mod)
    for path in py_files:
        mod = module_name(root, path)
        if not mod:
            continue
        internal, external = _collect_imports(path, mod)
        for name in internal:
            # Absolute imports may name the package itself ("sample.util");
            # module names here are relative to the package root, so strip it.
            if name == package:
                continue
            if name.startswith(package + "."):
                name = name[len(package) + 1:]
            # Keep the longest known module prefix (handles `from .x import y`).
            target = name
            while target and target not in graph.modules:
                target = target.rpartition(".")[0]
            if target:
                graph.edges[mod].add(target)
        for name in external:
            if name != package:
                graph.external[mod].add(name)
    return graph
