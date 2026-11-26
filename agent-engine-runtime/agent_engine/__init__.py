"""Agent Engine Runtime — core of an agent development platform.

Implements, in stdlib-only Python, the pieces the Atlas Agent Engine JD
calls out: a concurrent agent runtime, session memory (short-term working
memory + long-term episodic memory with retrieval), a retrieval layer over
a tool/knowledge index, and an identity & governance layer (scoped tool
authorization in MCP/A2A style, deny-by-default policy engine, and
multi-tenant isolation). All data is synthetic and seeded; no network,
no model calls, no credentials.
"""

from .runtime import AgentRuntime, AgentStep, AgentTask, RunResult, StepResult
from .memory import EpisodicMemory, SessionMemory, WorkingMemory
from .retrieval import KnowledgeIndex
from .governance import (
    Policy,
    PolicyEngine,
    TenantContext,
    ToolRegistry,
    ToolSpec,
)
from .sdk import Engine, demo_agent_steps

__all__ = [
    "AgentRuntime",
    "AgentStep",
    "AgentTask",
    "RunResult",
    "StepResult",
    "EpisodicMemory",
    "SessionMemory",
    "WorkingMemory",
    "KnowledgeIndex",
    "Policy",
    "PolicyEngine",
    "TenantContext",
    "ToolRegistry",
    "ToolSpec",
    "Engine",
    "demo_agent_steps",
]
