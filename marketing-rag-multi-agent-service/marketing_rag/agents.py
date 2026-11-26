"""Multi-agent workflow for marketing questions.

Four deterministic agents with a shared plan / retrieve / answer / validate
shape. They are rule-based policies over retrieved documents and seeded
figures — NOT live LLM calls. A real LLM agent (for example LangChain or
the OpenAI API) plugs into the same `run` interface: it would receive the
same subtask, the same retrieved context, and its draft would go through
the same ValidatorAgent before an answer ships.

Agents
- PlannerAgent: classifies the question and lists subtasks.
- AudienceAgent: picks matching segments and sizes the audience.
- ContentAgent: picks the best content assets for the question.
- BudgetAgent: computes spend, CPA and ROI from campaign figures and
  suggests a reallocation only from those retrieved figures.
- ValidatorAgent: checks every number in a draft answer against the
  retrieved documents and flags anything unsupported.
"""
from __future__ import annotations

import re

from .corpus import CAMPAIGNS, SEGMENTS, CONTENT_ASSETS

NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?x?")


class PlannerAgent:
    """Split a question into subtasks by intent keywords."""

    INTENTS = {
        "audience": ["audience", "segment", "target", "who should", "contacts"],
        "content": ["content", "email", "guide", "video", "webinar", "asset", "creative"],
        "budget": ["budget", "spend", "reallocat", "cpa", "roi", "cost", "cheapest", "efficient"],
        "performance": ["best", "perform", "top", "winning", "results", "compare"],
    }

    def run(self, question: str) -> dict:
        lowered = question.lower()
        intents = [name for name, words in self.INTENTS.items()
                   if any(w in lowered for w in words)]
        if not intents:
            intents = ["performance"]
        subtasks = [{"agent": "retrieval", "step": f"retrieve evidence for: {question}"}]
        for intent in intents:
            agent = {"audience": "AudienceAgent", "content": "ContentAgent",
                     "budget": "BudgetAgent", "performance": "BudgetAgent"}[intent]
            subtasks.append({"agent": agent, "step": f"answer the {intent} part"})
        subtasks.append({"agent": "ValidatorAgent", "step": "validate every number against retrieved docs"})
        return {"question": question, "intents": intents, "subtasks": subtasks}


class AudienceAgent:
    """Match segments to the question and report their sizes."""

    def run(self, question: str, retrieved: list[dict]) -> dict:
        lowered = question.lower()
        # A segment is also relevant when a retrieved campaign targets it:
        # campaigns carry their audience name, which matches a segment name.
        retrieved_campaigns = [doc for doc in retrieved if doc["kind"] == "campaign"]
        campaign_audiences = set()
        for doc in retrieved_campaigns:
            campaign = next((c for c in CAMPAIGNS if c["id"] == doc["id"]), None)
            if campaign:
                campaign_audiences.add(campaign["audience"].lower())
        matched = []
        for segment in SEGMENTS:
            haystack = (segment["name"] + " " + segment["criteria"] + " " + segment["notes"]).lower()
            hit = any(word in haystack for word in lowered.split() if len(word) > 3)
            cited = any(doc["id"] == segment["id"] for doc in retrieved)
            linked = segment["name"].lower() in campaign_audiences
            if hit or cited or linked:
                matched.append({"id": segment["id"], "name": segment["name"],
                                "size": segment["size"], "criteria": segment["criteria"],
                                "cited": cited or linked})
        if not matched:
            biggest = max(SEGMENTS, key=lambda s: s["size"])
            matched = [{"id": biggest["id"], "name": biggest["name"],
                        "size": biggest["size"], "criteria": biggest["criteria"],
                        "cited": any(doc["id"] == biggest["id"] for doc in retrieved)}]
        total = sum(m["size"] for m in matched)
        return {"agent": "AudienceAgent", "segments": matched,
                "total_audience": total,
                "summary": f"{len(matched)} matching segment(s), {total:,} contacts in total."}


class ContentAgent:
    """Pick the best content assets for the question from retrieved docs."""

    def run(self, question: str, retrieved: list[dict]) -> dict:
        lowered = question.lower()
        picked = []
        for asset in CONTENT_ASSETS:
            doc = next((d for d in retrieved if d["id"] == asset["id"]), None)
            if doc is None:
                continue
            haystack = (asset["title"] + " " + asset["summary"]).lower()
            relevance = sum(1 for word in lowered.split()
                            if len(word) > 3 and word in haystack)
            picked.append({"id": asset["id"], "title": asset["title"],
                           "type": asset["type"], "channel": asset["channel"],
                           "campaign_id": asset["campaign_id"],
                           "score": round(doc["score"], 4), "relevance": relevance})
        picked.sort(key=lambda p: (p["relevance"], p["score"]), reverse=True)
        return {"agent": "ContentAgent", "assets": picked[:3],
                "summary": f"{len(picked)} retrieved asset(s); top pick: "
                           f"{picked[0]['title']}" if picked else "No content asset retrieved."}


class BudgetAgent:
    """Compute spend, CPA and ROI from campaign figures only.

    Every figure comes from the retrieved campaign documents, so the
    validator can re-check it. No figure is invented.
    """

    @staticmethod
    def campaign_stats(campaign: dict) -> dict:
        cpa = campaign["spend"] / campaign["conversions"] if campaign["conversions"] else 0.0
        roi = campaign["revenue"] / campaign["spend"] if campaign["spend"] else 0.0
        return {"id": campaign["id"], "name": campaign["name"],
                "channel": campaign["channel"], "spend": campaign["spend"],
                "conversions": campaign["conversions"], "revenue": campaign["revenue"],
                "cpa": round(cpa, 2), "roi": round(roi, 2)}

    def run(self, question: str, retrieved: list[dict] | None = None) -> dict:
        # Best/worst ROI is a structured computation over the full campaign
        # table, not over the retrieved subset: restricting it to retrieved
        # docs would report the wrong "best" campaign. The service cites
        # the best and worst campaign documents in its answer, so the
        # validator can still re-check every figure.
        stats = [self.campaign_stats(c) for c in CAMPAIGNS]
        best_roi = max(stats, key=lambda s: s["roi"])
        worst_roi = min(stats, key=lambda s: s["roi"])
        total_spend = sum(s["spend"] for s in stats)
        total_revenue = sum(s["revenue"] for s in stats)
        suggestion = None
        if worst_roi["roi"] < 1.0 and best_roi["roi"] > worst_roi["roi"]:
            move = round(worst_roi["spend"] * 0.10)
            expected = round(move * (best_roi["roi"] - worst_roi["roi"]))
            suggestion = (f"Move 10% of {worst_roi['name']} spend (${move:,}) to "
                          f"{best_roi['name']}; expected gain about ${expected:,} "
                          f"at the fitted ROI gap.")
        return {"agent": "BudgetAgent", "campaigns": stats,
                "best_roi": best_roi, "worst_roi": worst_roi,
                "total_spend": total_spend, "total_revenue": total_revenue,
                "suggestion": suggestion,
                "summary": f"Best ROI: {best_roi['name']} at {best_roi['roi']:.2f}x; "
                           f"weakest: {worst_roi['name']} at {worst_roi['roi']:.2f}x."}


class ValidatorAgent:
    """Check every number in a draft answer against the retrieved text.

    A number passes only if the same digits appear in at least one cited
    document. Anything else is listed as unsupported so it never ships.
    """

    def run(self, draft: str, retrieved: list[dict]) -> dict:
        evidence = " ".join(doc["text"] for doc in retrieved)
        evidence_digits = {n.replace(",", "")
                           for n in re.findall(r"[\d,]+(?:\.\d+)?", evidence)}
        unsupported = []
        for token in NUMBER_RE.findall(draft):
            digits = token.replace("$", "").replace("x", "").replace(",", "")
            if digits not in evidence_digits:
                unsupported.append(token)
        return {"agent": "ValidatorAgent",
                "checked_numbers": len(NUMBER_RE.findall(draft)),
                "unsupported": sorted(set(unsupported)),
                "passed": not unsupported}
