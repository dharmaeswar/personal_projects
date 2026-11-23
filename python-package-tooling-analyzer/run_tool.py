"""End-to-end demo: analyze this project's own package with pkgtool."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pkgtool.api import extract_api_surface  # noqa: E402
from pkgtool.checks import run_checks  # noqa: E402
from pkgtool.cycles import find_cycles  # noqa: E402
from pkgtool.graph import build_graph  # noqa: E402
from pkgtool.report import text_report  # noqa: E402


def main() -> int:
    project_root = Path(__file__).resolve().parent
    graph = build_graph(project_root)
    cycles = find_cycles(graph)
    surface = extract_api_surface(project_root)
    checks = run_checks(project_root)
    print(text_report(graph, cycles, surface, checks))
    errors = [c for c in checks if c.level == "error"]
    return 1 if (errors or cycles) else 0


if __name__ == "__main__":
    raise SystemExit(main())
