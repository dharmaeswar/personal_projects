"""SDK surface: register agents and tools, run an agent, get a trace.

`Engine` is the one object a developer holds: it wires the runtime,
the session memory, the retrieval index, and the governed tool registry
together, and it exposes the small surface the CLI calls. Tool functions
here are the seeded demo tools (calculator, knowledge lookup, echo) —
real deployments plug in their own callables with the same signature.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .governance import Policy, PolicyEngine, TenantContext, ToolRegistry, ToolSpec
from .memory import SessionMemory
from .retrieval import Document, KnowledgeIndex
from .runtime import AgentRuntime, AgentStep, AgentTask, RunResult


def _calc(expression: str) -> float:
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        raise ValueError("calculator accepts digits and + - * / ( ) only")
    return float(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307


def _echo(text: str) -> str:
    return text


class Engine:
    """Developer-facing SDK for the agent engine runtime."""

    def __init__(self, tenant_id: str, principal: str,
                 scopes: Optional[List[str]] = None, max_workers: int = 4):
        self.ctx = TenantContext(
            tenant_id=tenant_id, principal=principal,
            scopes=frozenset(scopes or []),
        )
        self.policies = PolicyEngine()
        self.tools = ToolRegistry(policy_engine=self.policies)
        self.memory = SessionMemory(tenant_id=tenant_id)
        self.index = KnowledgeIndex()
        self.runtime = AgentRuntime(max_workers=max_workers)
        self._agents: Dict[str, List[AgentStep]] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        self.tools.register(ToolSpec(
            name="calculator", description="Evaluate a numeric expression.",
            required_scopes=frozenset({"tools:calc"}), fn=_calc))
        self.tools.register(ToolSpec(
            name="echo", description="Return the input text unchanged.",
            required_scopes=frozenset(), fn=_echo))

    def grant(self, policy: Policy) -> None:
        self.policies.add(policy)

    def register_tool(self, spec: ToolSpec) -> None:
        self.tools.register(spec)

    def register_agent(self, name: str, steps: List[AgentStep]) -> None:
        self._agents[name] = steps

    def add_knowledge(self, doc: Document) -> None:
        self.index.add(doc)

    def call_tool(self, tool_name: str, **kwargs) -> object:
        return self.tools.call(tool_name, self.ctx,
                               resource_tenant=self.ctx.tenant_id, **kwargs)

    def run(self, agent_name: str, max_steps: int = 50,
            context: Optional[Dict[str, object]] = None) -> RunResult:
        steps = self._agents.get(agent_name)
        if steps is None:
            raise ValueError(f"unknown agent {agent_name}")
        task = AgentTask(name=agent_name, steps=list(steps),
                         max_steps=max_steps, context=context or {})
        result = self.runtime.run(task)
        for step in result.steps:
            if step.status == "ok":
                self.memory.remember(
                    f"{agent_name}.{step.name} -> {step.value!r}")
        return result

    def agent_names(self) -> List[str]:
        return sorted(self._agents)

    def recall(self, query: str, top_k: int = 3):
        return self.memory.recall(query, top_k=top_k)

    def search(self, query: str, top_k: int = 3):
        return self.index.search(query, top_k=top_k)


def demo_agent_steps(engine: Engine) -> List[AgentStep]:
    """A seeded demo agent: recall history, retrieve knowledge, calculate."""

    def recall_step(ctx):
        hits = engine.recall(ctx.get("question", ""), top_k=2)
        return [h.episode.text for h in hits]

    def retrieve_step(ctx):
        hits = engine.search(ctx.get("question", ""), top_k=2)
        return [h.document.doc_id for h in hits]

    def calc_step(ctx):
        return engine.call_tool("calculator", expression="40 + 2")

    return [
        AgentStep(name="recall", fn=recall_step),
        AgentStep(name="retrieve", fn=retrieve_step),
        AgentStep(name="calculate", fn=calc_step),
    ]
