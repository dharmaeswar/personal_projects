"""Report rendering for pkgtool analysis results."""

from __future__ import annotations

import json

from pkgtool.api import ModuleApi
from pkgtool.checks import CheckResult
from pkgtool.graph import ImportGraph


def text_report(
    graph: ImportGraph,
    cycles: list[list[str]],
    surface: dict[str, ModuleApi],
    checks: list[CheckResult],
) -> str:
    lines = [f"Package: {graph.package} ({graph.root})", ""]
    lines.append(f"Modules: {len(graph.modules)}")
    lines.append(f"Internal edges: {sum(len(v) for v in graph.edges.values())}")
    lines.append("")
    lines.append("Import graph:")
    for mod in sorted(graph.modules):
        deps = sorted(graph.edges.get(mod, ()))
        lines.append(f"  {mod} -> {', '.join(deps) if deps else '(none)'}")
    lines.append("")
    lines.append("Dependency cycles:")
    if cycles:
        for c in cycles:
            lines.append("  " + " -> ".join(c + [c[0]]))
    else:
        lines.append("  none")
    lines.append("")
    lines.append("Public API surface:")
    for mod in sorted(surface):
        names = surface[mod].public_names
        lines.append(f"  {mod}: {', '.join(names) if names else '(none)'}")
    lines.append("")
    lines.append("Checks:")
    for c in checks:
        where = f" [{c.path}]" if c.path else ""
        lines.append(f"  [{c.level.upper()}] {c.code}: {c.message}{where}")
    return "\n".join(lines) + "\n"


def json_report(
    graph: ImportGraph,
    cycles: list[list[str]],
    surface: dict[str, ModuleApi],
    checks: list[CheckResult],
) -> str:
    payload = {
        "package": graph.package,
        "modules": sorted(graph.modules),
        "edges": {k: sorted(v) for k, v in sorted(graph.edges.items())},
        "external": {k: sorted(v) for k, v in sorted(graph.external.items())},
        "cycles": cycles,
        "api": {m: s.public_names for m, s in sorted(surface.items())},
        "checks": [
            {"code": c.code, "level": c.level, "message": c.message, "path": c.path} for c in checks
        ],
    }
    return json.dumps(payload, indent=2) + "\n"
