"""Agentic swarm orchestrator: fan out many agents over a large search space,
merge their partial results, verify them, and measure what it costs.

Standard library only. No live LLM calls: agents are deterministic simulated
models, so every run is reproducible offline.
"""

__all__ = ["corpus", "models", "orchestrator", "verify", "metrics"]
