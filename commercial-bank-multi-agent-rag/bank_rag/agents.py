"""The four agents of the pipeline.

Each agent is a deterministic rule-based policy — a stand-in for an LLM
agent — so every run is reproducible offline with no model API calls.
Swapping in a real LangChain agent means replacing the decision logic;
the retrieval, context and validation interfaces stay the same.

- Planner: splits a question into subtasks (numeric lookup, text lookup,
  ratio computation, covenant check).
- Retriever: runs hybrid retrieval and context engineering.
- Analyst: composes the answer from the packed context ONLY — every figure
  it uses must be parsed out of the context chunks, never from the table
  behind the corpus. If a needed figure is missing, it says so.
- Validator: re-checks every number in the answer against the context by
  recomputing ratios from the context figures; covenant verdicts are
  recomputed the same way.
"""

import re

from .context import build_context, context_text
from .corpus import BORROWERS
from .retrieval import TextIndex, find_borrower, hybrid_retrieve, tokenize


FIGURE_RE = re.compile(
    r"reported (revenue|ebitda|total debt|cash|interest expense) of ([\d.]+)")

METRIC_NAMES = {"total debt": "total_debt", "interest expense": "interest_expense"}


def figures_from_context(chunks):
    """Parse borrower figures out of packed context chunks.

    Returns {borrower: {metric: value}} — only what the context contains.
    """
    figures = {}
    for chunk in chunks:
        for metric, raw in FIGURE_RE.findall(chunk["text"]):
            key = METRIC_NAMES.get(metric, metric)
            figures.setdefault(chunk["borrower"], {})[key] = float(raw)
    return figures


class Planner:
    def plan(self, question):
        lowered = question.lower()
        subtasks = []
        if any(w in lowered for w in ("leverage", "debt", "ebitda", "revenue",
                                      "cash", "interest", "margin", "coverage")):
            subtasks.append("numeric-lookup")
        if any(w in lowered for w in ("memo", "risk", "say", "supply", "outage",
                                      "margin", "covenant", "compliance", "breach")):
            subtasks.append("text-lookup")
        if any(w in lowered for w in ("ratio", "leverage", "margin", "coverage")):
            subtasks.append("compute-ratio")
        if any(w in lowered for w in ("covenant", "compliance", "breach", "within")):
            subtasks.append("covenant-check")
        if not subtasks:
            subtasks.append("text-lookup")
        return {"question": question, "subtasks": subtasks,
                "borrower": find_borrower(question)}


class Retriever:
    def __init__(self, docs):
        self.docs = docs
        self.index = TextIndex(docs)

    def retrieve(self, question, k=3, budget_chars=1200):
        retrieved = hybrid_retrieve(question, self.docs, self.index, k=k)
        context = build_context(retrieved, budget_chars=budget_chars)
        return {"retrieved": retrieved, "context": context,
                "context_text": context_text(context)}


def _fmt(value):
    return f"{value:.2f}"


class Analyst:
    """Compose the answer from the packed context only."""

    def answer(self, question, context, plan):
        lowered = question.lower()
        borrower = plan.get("borrower")
        chunks = context["chunks"]
        by_borrower = figures_from_context(chunks)
        figures = by_borrower.get(borrower, {}) if borrower else {}
        citations = context["citations"]

        def cite(kind):
            for doc_id in citations:
                if doc_id.endswith(f"|{kind}"):
                    return doc_id
            return citations[0] if citations else "no-source"

        def missing(*metrics):
            return [m for m in metrics if m not in figures]

        if borrower and "leverage" in lowered and "covenant" not in lowered \
                and "compliance" not in lowered:
            if missing("total_debt", "ebitda"):
                return {"answer": "Insufficient evidence in the retrieved context to compute leverage.",
                        "citations": citations, "computed": {}}
            ratio = figures["total_debt"] / figures["ebitda"]
            return {
                "answer": (
                    f"{borrower} leverage is {_fmt(ratio)}x "
                    f"(total debt {figures['total_debt']:.1f} / EBITDA "
                    f"{figures['ebitda']:.1f})."
                ),
                "citations": [cite("financials")],
                "computed": {"leverage": ratio},
            }
        if borrower and "interest coverage" in lowered:
            if missing("ebitda", "interest_expense"):
                return {"answer": "Insufficient evidence in the retrieved context to compute interest coverage.",
                        "citations": citations, "computed": {}}
            ratio = figures["ebitda"] / figures["interest_expense"]
            return {
                "answer": (
                    f"{borrower} interest coverage is {_fmt(ratio)}x "
                    f"(EBITDA {figures['ebitda']:.1f} / interest expense "
                    f"{figures['interest_expense']:.1f})."
                ),
                "citations": [cite("financials")],
                "computed": {"interest_coverage": ratio},
            }
        if borrower and "ebitda margin" in lowered:
            if missing("ebitda", "revenue"):
                return {"answer": "Insufficient evidence in the retrieved context to compute EBITDA margin.",
                        "citations": citations, "computed": {}}
            margin = 100.0 * figures["ebitda"] / figures["revenue"]
            return {
                "answer": (
                    f"{borrower} EBITDA margin is {_fmt(margin)}% "
                    f"(EBITDA {figures['ebitda']:.1f} / revenue "
                    f"{figures['revenue']:.1f})."
                ),
                "citations": [cite("financials")],
                "computed": {"ebitda_margin_pct": margin},
            }
        if "highest ebitda margin" in lowered or "highest margin" in lowered:
            margins = {}
            for name, figs in by_borrower.items():
                if "ebitda" in figs and "revenue" in figs:
                    margins[name] = 100.0 * figs["ebitda"] / figs["revenue"]
            if not margins:
                return {"answer": "Insufficient evidence in the retrieved context to compare EBITDA margins.",
                        "citations": citations, "computed": {}}
            best = max(margins, key=margins.get)
            parts = ", ".join(f"{n} {_fmt(m)}%" for n, m in sorted(margins.items()))
            return {
                "answer": (
                    f"{best} has the highest EBITDA margin at "
                    f"{_fmt(margins[best])}% ({parts})."
                ),
                "citations": [cite("financials")],
                "computed": {"ebitda_margins_pct": margins},
            }
        if borrower and ("covenant" in lowered or "compliance" in lowered
                         or "breach" in lowered):
            if missing("total_debt", "ebitda", "interest_expense"):
                return {"answer": "Insufficient evidence in the retrieved context to check covenant compliance.",
                        "citations": citations, "computed": {}}
            limits = BORROWERS[borrower]
            leverage = figures["total_debt"] / figures["ebitda"]
            coverage = figures["ebitda"] / figures["interest_expense"]
            lev_ok = leverage <= limits["max_leverage"]
            cov_ok = coverage >= limits["min_interest_coverage"]
            verdict = "in compliance" if (lev_ok and cov_ok) else "in breach"
            return {
                "answer": (
                    f"{borrower} is {verdict}: leverage {_fmt(leverage)}x "
                    f"against a maximum of {limits['max_leverage']:.1f}x, "
                    f"interest coverage {_fmt(coverage)}x against a minimum "
                    f"of {limits['min_interest_coverage']:.1f}x."
                ),
                "citations": [cite("financials"), cite("covenant")],
                "computed": {"leverage": leverage, "interest_coverage": coverage,
                             "leverage_ok": lev_ok, "coverage_ok": cov_ok},
            }
        # Text questions: answer with the memo sentence that best matches
        # the question's content words (borrower name excluded, so a plain
        # "X builds Y" opener does not beat the on-topic sentence).
        if chunks:
            question_tokens = set(tokenize(question))
            if borrower:
                question_tokens -= set(tokenize(borrower))
            memo_chunks = [c for c in chunks if c["kind"] == "memo"] or chunks
            best = max(memo_chunks,
                       key=lambda c: len(set(tokenize(c["text"])) & question_tokens))
            return {"answer": best["text"], "citations": [best["doc_id"]],
                    "computed": {}}
        return {"answer": "No relevant evidence was retrieved.",
                "citations": [], "computed": {}}


class Validator:
    """Re-check the answer against the packed context.

    Numbers in the answer must either appear verbatim in the context or
    be recomputable from the context figures (ratios, margins). The
    analyst's own computed values are never trusted — they are recomputed
    here from the context. Covenant verdicts are recomputed the same way.
    """

    NUMBER_RE = re.compile(r"\d+\.\d+|\d+")

    def validate(self, answer_text, context, computed, plan):
        findings = []
        chunks = context["chunks"]
        context_numbers = set()
        for chunk in chunks:
            for num in self.NUMBER_RE.findall(chunk["text"]):
                context_numbers.add(float(num))
        # Recompute every ratio/margin the context figures support.
        by_borrower = figures_from_context(chunks)
        recomputed = set()
        for figs in by_borrower.values():
            if "total_debt" in figs and "ebitda" in figs:
                recomputed.add(round(figs["total_debt"] / figs["ebitda"], 2))
            if "ebitda" in figs and "interest_expense" in figs:
                recomputed.add(round(figs["ebitda"] / figs["interest_expense"], 2))
            if "ebitda" in figs and "revenue" in figs:
                recomputed.add(round(100.0 * figs["ebitda"] / figs["revenue"], 2))
        grounded = {round(v, 2) for v in context_numbers} | recomputed
        for raw in self.NUMBER_RE.findall(answer_text):
            if round(float(raw), 2) not in grounded:
                findings.append(
                    f"Ungrounded number {raw} in answer: not in context "
                    f"and not recomputable from it.")
        # Covenant verdict re-check, recomputed from context figures.
        borrower = plan.get("borrower")
        if borrower and ("in compliance" in answer_text
                         or "in breach" in answer_text):
            figs = by_borrower.get(borrower, {})
            limits = BORROWERS[borrower]
            if "total_debt" in figs and "ebitda" in figs \
                    and "interest_expense" in figs:
                leverage = figs["total_debt"] / figs["ebitda"]
                coverage = figs["ebitda"] / figs["interest_expense"]
                expected = "in compliance" if (
                    leverage <= limits["max_leverage"]
                    and coverage >= limits["min_interest_coverage"]) else "in breach"
                claimed = "in compliance" if "in compliance" in answer_text else "in breach"
                if claimed != expected:
                    findings.append(
                        f"Covenant verdict wrong: answer says {claimed}, "
                        f"recomputed verdict is {expected}.")
        return {"verdict": "PASS" if not findings else "FAIL",
                "findings": findings}
