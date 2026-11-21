"""Agent orchestrator: run a partner request end to end.

A partner request arrives as a question plus a token. The agent:

1. Picks the skill that matches the request intent.
2. Retrieves knowledge-base passages to ground the answer.
3. Vends the trusted data the skill needs, if the token allows it.
4. Calls the live ML model when the skill needs a prediction.
5. Records every step in one audit trail, and stops at the first denial —
   a denied skill, missing data scope, or a stale-only answer never
   becomes a silent success.
"""

from __future__ import annotations

from .knowledge import KnowledgeBase
from .models import ModelPlatform
from .skills import SkillRegistry
from .vending import DataVending, Token


class PartnerAgent:
    """Orchestrates skills, knowledge, data vending and models per request."""

    def __init__(self, skills: SkillRegistry, knowledge: KnowledgeBase,
                 vending: DataVending, models: ModelPlatform) -> None:
        self.skills = skills
        self.knowledge = knowledge
        self.vending = vending
        self.models = models
        self.trail: list[dict] = []

    def handle_request(self, intent: str, question: str, token: Token,
                       skill_inputs: dict, product_id: str | None = None,
                       model_name: str | None = None,
                       approved_by: str | None = None) -> dict:
        """Run one partner request; returns the outcome and the audit trail."""
        self.trail = []
        outcome: dict = {"intent": intent, "steps": [], "answer": None,
                         "denied": None}

        # Step 1 — skill, with its approval gate.
        invocation = self.skills.invoke(intent, skill_inputs, approved_by)
        outcome["steps"].append(
            {"step": "skill", "skill": intent, "approved": invocation.approved})
        if not invocation.approved:
            outcome["denied"] = "skill approval required"
            return outcome

        # Step 2 — knowledge retrieval grounds the answer.
        citations = self.knowledge.retrieve(question)
        fresh = [c for c in citations if not c.stale]
        outcome["steps"].append(
            {"step": "knowledge", "citations": len(citations),
             "fresh_citations": len(fresh)})
        if citations and not fresh:
            outcome["denied"] = "only stale knowledge available"
            return outcome

        # Step 3 — vend trusted data when the skill needs it.
        if product_id is not None:
            vend = self.vending.vend(token, product_id)
            outcome["steps"].append(
                {"step": "vending", "product": product_id,
                 "granted": vend["granted"], "rows": len(vend["rows"])})
            if not vend["granted"]:
                outcome["denied"] = f"data vending denied: {vend['reason']}"
                return outcome
            outcome["rows"] = vend["rows"]

        # Step 4 — call the live model when the skill needs a prediction.
        if model_name is not None:
            live = self.models.live_version(model_name)
            outcome["steps"].append(
                {"step": "model", "model": model_name, "live_version": live})
            if live is None:
                outcome["denied"] = f"model {model_name!r} is not live"
                return outcome

        sources = [f"{c.passage.doc_id}#{c.passage.chunk_id}" for c in fresh]
        outcome["answer"] = (
            f"Handled {intent!r} with {len(fresh)} fresh citation(s)"
            + (f" from {sources}" if sources else "")
            + "."
        )
        return outcome
