"""AI SDLC agent platform: agentic workflows across the software development
lifecycle — code generation, review, testing and release — with graph-based
context grounding, capability-aware model routing, and benchmark suites
graded on real-world tasks.
"""

from .agents import CodeGenAgent, ReleaseAgent, ReviewAgent, TestAgent, run_sdlc
from .benchmarks import ab_compare, pareto_frontier, run_suite
from .context_graph import ContextGraph
from .observability import dashboard, init_db
from .routing import Model, ModelRouter
from .tools import ToolServer

__all__ = [
    "CodeGenAgent", "ReleaseAgent", "ReviewAgent", "TestAgent", "run_sdlc",
    "ab_compare", "pareto_frontier", "run_suite", "ContextGraph",
    "dashboard", "init_db", "Model", "ModelRouter", "ToolServer",
]
