"""Ask pipeline: plan -> retrieve -> agents -> validate -> answer.

The answer text uses only numbers that appear verbatim in the cited
documents, so ValidatorAgent can re-check every figure. Computed values
(audience totals, reallocation amounts) are returned separately and marked
derived, never smuggled into the answer as if they were retrieved facts.

Citations are ordered with the documents the answer actually quotes first
(best/worst campaigns, cited segments, top content asset), then the rest of
the retrieved set.
"""
from __future__ import annotations

from .agents import (AudienceAgent, BudgetAgent, ContentAgent, PlannerAgent,
                     ValidatorAgent)
from .corpus import CAMPAIGNS, build_documents
from .retrieval import Retriever


class MarketingRagService:
    def __init__(self, docs: list[dict] | None = None):
        self.docs = docs if docs is not None else build_documents()
        self._docs_by_id = {d["id"]: d for d in self.docs}
        self.retriever = Retriever(self.docs)
        self.planner = PlannerAgent()
        self.audience = AudienceAgent()
        self.content = ContentAgent()
        self.budget = BudgetAgent()
        self.validator = ValidatorAgent()

    def ask(self, question: str, top_k: int = 5) -> dict:
        if not question or not question.strip():
            return {"question": question, "answer": "Please ask a marketing question.",
                    "citations": [], "intents": [], "trace": [], "validation": {"passed": True,
                    "checked_numbers": 0, "unsupported": []}, "derived": {}}
        plan = self.planner.run(question)
        retrieved = self.retriever.retrieve(question, top_k=top_k)
        audience = self.audience.run(question, retrieved)
        content = self.content.run(question, retrieved)
        budget = self.budget.run(question)

        quoted_ids: list[str] = []
        lines = []
        if "audience" in plan["intents"]:
            for seg in audience["segments"]:
                if not seg["cited"]:
                    continue  # never quote a segment the retrieval did not return
                quoted_ids.append(seg["id"])
                lines.append(f"Audience: {seg['name']} has {seg['size']:,} contacts "
                             f"({seg['criteria']}).")
        if "content" in plan["intents"] and content["assets"]:
            top = content["assets"][0]
            quoted_ids.append(top["id"])
            campaign_name = next((c["name"] for c in CAMPAIGNS
                                  if c["id"] == top["campaign_id"]), None)
            if campaign_name:
                quoted_ids.append(top["campaign_id"])
                lines.append(f"Content: the best matching asset is {top['title']} "
                             f"({top['type']}, {top['channel']}), from the "
                             f"{campaign_name} campaign.")
            else:
                lines.append(f"Content: the best matching asset is {top['title']} "
                             f"({top['type']}, {top['channel']}).")
        if "budget" in plan["intents"] or "performance" in plan["intents"]:
            best, worst = budget["best_roi"], budget["worst_roi"]
            quoted_ids.extend([best["id"], worst["id"]])
            lines.append(f"Budget: best return is {best['name']} at {best['roi']:.2f}x "
                         f"(spend ${best['spend']:,}, revenue ${best['revenue']:,}); "
                         f"weakest is {worst['name']} at {worst['roi']:.2f}x "
                         f"(spend ${worst['spend']:,}, revenue ${worst['revenue']:,}).")
        if not lines:
            lines.append("No matching campaign, segment or content was retrieved "
                         "for this question.")
        answer = " ".join(lines)

        # Citations: quoted documents first (in answer order), then the rest.
        seen: set[str] = set()
        citations = []
        for doc_id in quoted_ids:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            doc = self._docs_by_id[doc_id]
            score = next((r["score"] for r in retrieved if r["id"] == doc_id),
                         self.retriever.score_for(doc_id, question))
            citations.append({"id": doc["id"], "kind": doc["kind"], "score": score})
        for doc in retrieved:
            if doc["id"] not in seen:
                seen.add(doc["id"])
                citations.append({"id": doc["id"], "kind": doc["kind"], "score": doc["score"]})
        evidence = [self._docs_by_id[c["id"]] for c in citations]
        validation = self.validator.run(answer, evidence)
        return {
            "question": question,
            "answer": answer,
            "citations": citations,
            "intents": plan["intents"],
            "trace": [step for step in plan["subtasks"]],
            "validation": validation,
            "derived": {
                "total_audience": audience["total_audience"],
                "budget_suggestion": budget["suggestion"],
                "total_spend": budget["total_spend"],
                "total_revenue": budget["total_revenue"],
                "note": "Derived by arithmetic from retrieved figures; not quoted as retrieved facts.",
            },
        }
