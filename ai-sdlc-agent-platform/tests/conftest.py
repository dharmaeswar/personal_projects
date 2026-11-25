import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdlc_agents.context_graph import ContextGraph, Node  # noqa: E402


def make_graph() -> ContextGraph:
    graph = ContextGraph()
    graph.add_node(Node("file:billing.py", "file", "billing.py", "billing average charge"))
    graph.add_node(Node("fn:average", "function", "average", "average total count mean"))
    graph.add_node(Node("test:test_average", "test", "test_average", "test average total"))
    graph.add_node(Node("ticket:SDLC-101", "ticket", "SDLC-101", "fix average off-by-one"))
    graph.add_edge("file:billing.py", "fn:average", "defines")
    graph.add_edge("test:test_average", "fn:average", "tested_by")
    graph.add_edge("ticket:SDLC-101", "fn:average", "fixes")
    return graph
