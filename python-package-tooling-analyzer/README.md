# Python Package Tooling Analyzer

A developer tool that analyzes a Python package the way a language-ecosystem
/ build-tools team would: it builds the import graph, finds dependency cycles,
extracts the public API surface, and runs build-metadata and lint checks.
Library + CLI, standard library only.

## What it does

- **Import graph** (`pkgtool/graph.py`) — walks a package directory, parses
  every `.py` file with `ast`, resolves relative imports to dotted names,
  and records intra-package edges plus external (stdlib / third-party) imports.
- **Cycle detection** (`pkgtool/cycles.py`) — Tarjan's strongly-connected
  components over the import graph; each cycle is reported as a closed loop.
- **API surface** (`pkgtool/api.py`) — per module, the public functions,
  classes and constants, honoring `__all__` when a module defines one.
- **Build checks** (`pkgtool/checks.py`) — packaging metadata (`pyproject.toml`
  / `setup.py`), README presence, `__init__.py` layout, `tests/` layout,
  wildcard imports and unused imports.
- **Reports** (`pkgtool/report.py`) — plain-text and JSON output.

## Usage

```bash
# Full analysis (text report; exit 1 if cycles or check errors exist)
python -m pkgtool.cli analyze path/to/package

# JSON report to a file
python -m pkgtool.cli analyze path/to/package --format json --out report.json

# Just cycles, API surface, or checks
python -m pkgtool.cli cycles path/to/package
python -m pkgtool.cli api path/to/package
python -m pkgtool.cli check path/to/package

# Demo: analyze this project's own package
python run_tool.py
```

## Example output

```
Package: pkgtool (...)
Modules: 6
Internal edges: 5

Dependency cycles:
  none

Public API surface:
  api: ApiMember, ModuleApi, extract_api_surface
  ...

Checks:
  [OK] PKG001: packaging metadata present: pyproject.toml
  [OK] PKG002: README present
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```

25 tests: graph construction (5), cycle detection (5), API surface (3),
build checks (6), CLI (6). All pass. The demo (`python run_tool.py`)
analyzes this project's own tree and reports no cycles and no check errors.
