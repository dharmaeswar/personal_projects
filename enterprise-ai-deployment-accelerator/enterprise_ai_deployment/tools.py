"""MCP-style tool registry for enterprise integrations.

Enterprise agents do not answer from a model alone: they call the
customer's systems. Each tool has a name, a description and a typed
input schema; arguments are validated before dispatch and every call is
traced, so a deployment can be audited end to end.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Tool:
    """One callable enterprise tool."""

    name: str
    description: str
    required_inputs: list  # input names that must be supplied
    handler: object  # callable(**inputs) -> result


@dataclass
class ToolRegistry:
    """Named tools with schema validation and a full call trace."""

    tools: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self.tools[tool.name] = tool

    def call(self, tool_name: str, **inputs):
        """Validate inputs, dispatch, trace the call, return the result."""
        if tool_name not in self.tools:
            raise ValueError(f"unknown tool: {tool_name}")
        tool = self.tools[tool_name]
        missing = [name for name in tool.required_inputs if name not in inputs]
        if missing:
            raise ValueError(
                f"tool {tool_name} missing required inputs: {missing}")
        start = time.monotonic()
        result = tool.handler(**inputs)
        self.trace.append({
            "tool": tool_name,
            "inputs": inputs,
            "output": result,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        })
        return result


def build_enterprise_tools(store) -> ToolRegistry:
    """Standard tools for a mid-market deployment, backed by a DocStore.

    - search_kb: retrieve passages for a question.
    - lookup_policy: fetch one document by id (governance check).
    - escalate_to_human: hand a case to a person with a reason.
    - log_feedback: record a thumbs up/down on an answer.
    """
    registry = ToolRegistry()

    def search_kb(query, top_k=3):
        hits = store.search(query, top_k=top_k)
        return [{"doc_id": h.doc_id, "title": h.title, "score": h.score}
                for h in hits]

    def lookup_policy(doc_id):
        for doc in store.docs:
            if doc.doc_id == doc_id:
                return {"doc_id": doc.doc_id, "title": doc.title,
                        "text": doc.text}
        return {"error": f"no policy document {doc_id}"}

    def escalate_to_human(reason, question):
        return {"escalated": True, "reason": reason, "question": question}

    def log_feedback(answer_id, helpful):
        return {"answer_id": answer_id, "helpful": bool(helpful),
                "recorded": True}

    registry.register(Tool("search_kb",
                           "Search the enterprise knowledge base.",
                           ["query"], search_kb))
    registry.register(Tool("lookup_policy",
                           "Fetch one policy document by id.",
                           ["doc_id"], lookup_policy))
    registry.register(Tool("escalate_to_human",
                           "Hand a question to a human with a reason.",
                           ["reason", "question"], escalate_to_human))
    registry.register(Tool("log_feedback",
                           "Record whether an answer was helpful.",
                           ["answer_id", "helpful"], log_feedback))
    return registry
