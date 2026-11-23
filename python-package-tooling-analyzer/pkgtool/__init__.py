"""pkgtool — a developer tool that analyzes Python packages.

Builds an import graph, finds dependency cycles, extracts the public
API surface, and runs build-metadata / lint checks. Library + CLI.
"""

from pkgtool.graph import ImportGraph, build_graph
from pkgtool.cycles import find_cycles
from pkgtool.api import extract_api_surface
from pkgtool.checks import run_checks

__all__ = ["ImportGraph", "build_graph", "find_cycles", "extract_api_surface", "run_checks"]
__version__ = "1.0.0"
