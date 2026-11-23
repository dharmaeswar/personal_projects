"""Public API-surface extraction for a Python package.

For every module, lists the names a user of the package can rely on:
top-level functions, classes and assigned constants, honoring
``__all__`` when a module defines one. Private names (leading ``_``)
are excluded unless explicitly listed in ``__all__``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from pkgtool.graph import module_name


@dataclass
class ApiMember:
    name: str
    kind: str  # "function" | "class" | "constant"
    line: int


@dataclass
class ModuleApi:
    module: str
    members: list[ApiMember] = field(default_factory=list)
    has_all: bool = False

    @property
    def public_names(self) -> list[str]:
        return [m.name for m in self.members]


def _module_api(path: Path, mod: str) -> ModuleApi:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    declared_all: list[str] | None = None
    members: list[ApiMember] = []
    imported: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[alias.asname or alias.name.split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imported[alias.asname or alias.name] = node.lineno
        if isinstance(node, ast.FunctionDef):
            members.append(ApiMember(node.name, "function", node.lineno))
        elif isinstance(node, ast.AsyncFunctionDef):
            members.append(ApiMember(node.name, "function", node.lineno))
        elif isinstance(node, ast.ClassDef):
            members.append(ApiMember(node.name, "class", node.lineno))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    members.append(ApiMember(target.id, "constant", node.lineno))
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__all__"
                and isinstance(node.value, (ast.List, ast.Tuple))
            ):
                declared_all = [
                    e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
                ]
    if declared_all is not None:
        by_name = {m.name: m for m in members}
        resolved = []
        for n in declared_all:
            if n in by_name:
                resolved.append(by_name[n])
            elif n in imported:
                resolved.append(ApiMember(n, "import", imported[n]))
        return ModuleApi(module=mod, members=resolved, has_all=True)
    public = [m for m in members if not m.name.startswith("_")]
    return ModuleApi(module=mod, members=public, has_all=False)


def extract_api_surface(package_dir: str | Path) -> dict[str, ModuleApi]:
    """Map module name -> its public API for the package at ``package_dir``."""
    root = Path(package_dir).resolve()
    surface: dict[str, ModuleApi] = {}
    for path in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        mod = module_name(root, path)
        if mod:
            surface[mod] = _module_api(path, mod)
    return surface
