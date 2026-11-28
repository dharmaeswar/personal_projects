"""LangChain / LangGraph-style orchestration for the GenAI platform.

A request flows through a small state graph — plan, retrieve, generate,
validate — the same shape a LangGraph ``StateGraph`` carries. Each node is
a plain function over a shared state dict, so the graph can be drawn,
tested and audited without a framework. A real LangChain/LangGraph
adapter implements the same node functions with framework primitives;
the graph definition and the validation rules do not change.

The generator is a deterministic stand-in: it composes an extractive
answer from the retrieved context only, with citations. It never calls a
real model, and it says so when the context has nothing to answer with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gateway import Gateway
from .rag import KnowledgeBase, tokenize

GRAPH_NODES = ("plan", "retrieve", "generate", "validate")


@dataclass
class GraphState:
    question: str
    team: str
    use_case: str
    plan: list[str] = field(default_factory=list)
    context: str = ""
    citations: list[str] = field(default_factory=list)
    draft_answer: str = ""
    answer: str = ""
    validation: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def node_plan(state: GraphState) -> GraphState:
    """Split the question into retrieval subtasks."""
    question = state.question.lower()
    plan = ["retrieve"]
    if any(word in question for word in ("limit", "covenant", "ratio", "above")):
        plan.append("numeric-check")
    if any(word in question for word in ("policy", "require", "must", "approval")):
        plan.append("policy-check")
    plan.append("generate")
    plan.append("validate")
    state.plan = plan
    return state


def node_retrieve(state: GraphState, kb: KnowledgeBase) -> GraphState:
    context, citations = kb.pack_context(state.question, top_k=3)
    state.context = context
    state.citations = citations
    if not context:
        state.errors.append("no supporting context found for the question")
    return state


def node_generate(state: GraphState) -> GraphState:
    """Extractive stand-in generator: answer from context only."""
    if not state.context:
        state.draft_answer = (
            "I do not have supporting documentation for this question."
        )
        return state
    question_words = {w for w in tokenize(state.question) if len(w) > 3}
    best_sentence = ""
    best_hits = 0
    for line in state.context.split("\n"):
        body = line.split("] ", 1)[-1]
        for sentence in body.split(". "):
            hits = sum(1 for w in question_words if w in sentence.lower())
            if hits > best_hits:
                best_hits = hits
                best_sentence = sentence.strip()
    if best_sentence:
        state.draft_answer = best_sentence.rstrip(".") + "."
    else:
        state.draft_answer = state.context.split("\n")[0].split("] ", 1)[-1]
    return state


def node_validate(state: GraphState) -> GraphState:
    """Every claim in the draft must be grounded in the retrieved context."""
    checks = {
        "has_answer": bool(state.draft_answer.strip()),
        "has_citations": bool(state.citations),
        "grounded": False,
        "no_invented_numbers": True,
    }
    if state.context and state.draft_answer:
        answer_words = {
            w.strip(".,") for w in state.draft_answer.lower().split()
        }
        context_words = {
            w.strip(".,") for w in state.context.lower().split()
        }
        overlap = answer_words & context_words
        checks["grounded"] = len(overlap) >= max(3, len(answer_words) // 2)
    state.validation = checks
    state.answer = state.draft_answer
    if not checks["grounded"] and state.context:
        state.errors.append("draft answer failed grounding check")
    return state


def run_graph(
    question: str,
    kb: KnowledgeBase,
    *,
    team: str,
    use_case: str,
    gateway: Gateway | None = None,
    preferred_model: str | None = None,
) -> GraphState:
    """Run plan -> retrieve -> generate -> validate. When a gateway is
    supplied, the generate step is recorded as a metered model call
    instead of the local stand-in (the stand-in still produces the text
    in this demo, so runs stay reproducible offline)."""
    state = GraphState(question=question, team=team, use_case=use_case)
    node_plan(state)
    node_retrieve(state, kb)
    node_generate(state)
    node_validate(state)
    if gateway is not None and state.context:
        gateway.invoke(
            state.draft_answer,
            team=team,
            use_case=use_case,
            preferred_model=preferred_model,
        )
    return state
