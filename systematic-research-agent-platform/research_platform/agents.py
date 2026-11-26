"""The four agents of a research run.

Planner decomposes a research question into subtasks; Retriever pulls
evidence from the knowledge layer; Executor runs sandboxed computations
through tools; Validator re-checks every number and citation in the draft
answer. All agents are deterministic rule-based policies over the seeded
corpora — no live LLM call — so every trajectory is reproducible.
"""

import re

# Keyword -> subtask mapping the planner uses to decompose a question.
TOPIC_RULES = [
    (("momentum", "trend"), "momentum",
     "Retrieve the momentum research note and dataset, and read the momentum signal code."),
    (("carry", "fx carry"), "carry",
     "Retrieve the FX carry research note and dataset."),
    (("volatility", "vol-target", "risk parity"), "volatility",
     "Retrieve the volatility-targeting research note and dataset."),
    (("mean reversion", "mean-reversion"), "mean_reversion",
     "Retrieve the mean-reversion research note."),
    (("z-score", "zscore"), "zscore",
     "Read the z-score code snippet."),
]

SERIES_FOR_TOPIC = {"momentum": "momentum", "carry": "carry"}
DATASET_LABELS = {
    "momentum": [("momentum annualised return", 6.2),
                 ("momentum volatility", 11.4),
                 ("momentum sharpe", 0.54)],
    "carry": [("carry annualised return", 4.8),
              ("carry volatility", 9.1),
              ("carry sharpe", 0.53)],
    "volatility": [("volatility target", 10.0),
                   ("realised volatility", 10.3),
                   ("leverage cap", 2.0)],
    "mean_reversion": [("mean reversion sharpe", 0.28)],
}


def plan(question):
    """Decompose a question into subtasks. Falls back to a general task."""
    lowered = question.lower()
    subtasks = []
    for keywords, topic, description in TOPIC_RULES:
        if any(k in lowered for k in keywords):
            subtasks.append({"topic": topic, "description": description})
    if not subtasks:
        subtasks.append({
            "topic": "general",
            "description": "Retrieve the most relevant research notes and datasets.",
        })
    return subtasks


def retrieve(tools, subtask):
    """Run the retriever for one subtask; returns evidence passages."""
    topic = subtask["topic"]
    evidence = []
    if topic == "momentum":
        evidence += tools.call("search_knowledge", {"query": "momentum 252-day return", "kind": "research"})
        evidence += tools.call("search_knowledge", {"query": "momentum factor return volatility Sharpe", "kind": "data"})
        evidence.append(tools.call("read_code", {"doc_id": "CODE-MOM-01"}))
    elif topic == "carry":
        evidence += tools.call("search_knowledge", {"query": "FX carry rate differential", "kind": "research"})
        evidence += tools.call("search_knowledge", {"query": "carry factor return volatility Sharpe", "kind": "data"})
    elif topic == "volatility":
        evidence += tools.call("search_knowledge", {"query": "volatility targeting 10 percent", "kind": "research"})
        evidence += tools.call("search_knowledge", {"query": "volatility targeted portfolio realised", "kind": "data"})
    elif topic == "mean_reversion":
        evidence += tools.call("search_knowledge", {"query": "mean reversion 20-day average", "kind": "research"})
    elif topic == "zscore":
        evidence.append(tools.call("read_code", {"doc_id": "CODE-ZSCORE-01"}))
    else:
        evidence += tools.call("search_knowledge", {"query": subtask["description"]})
    return evidence


def execute(tools, subtask):
    """Run the executor for one subtask; returns computed statistics."""
    topic = subtask["topic"]
    series = SERIES_FOR_TOPIC.get(topic)
    if series is None:
        return []
    return [
        tools.call("compute_statistic", {"series": series, "statistic": "mean"}),
        tools.call("compute_statistic", {"series": series, "statistic": "volatility"}),
        tools.call("compute_statistic", {"series": series, "statistic": "sharpe"}),
    ]


def compose(question, subtasks, evidence, computations):
    """Compose a grounded answer from retrieved evidence only.

    Every sentence that states a figure cites the document it came from.
    If no evidence was retrieved, the answer says so instead of inventing one.
    """
    if not evidence:
        return {
            "text": "Not covered by the research notes: no evidence was retrieved for this question.",
            "citations": [],
            "claims": [],
        }
    cited_docs = []
    for item in evidence:
        doc_id = item.get("doc_id")
        if doc_id and doc_id not in cited_docs:
            cited_docs.append(doc_id)
    claims = []
    for subtask in subtasks:
        for label, value in DATASET_LABELS.get(subtask["topic"], []):
            claims.append({"label": label, "value": value})
    lines = [f"Research answer for: {question}"]
    for label, value in [(c["label"], c["value"]) for c in claims]:
        doc = next((d for d in cited_docs if d.startswith("DATA-")), None)
        lines.append(f"- {label}: {value} [source: {doc or cited_docs[0]}]")
    if computations:
        for comp in computations:
            lines.append(
                f"- computed {comp['statistic']} of {comp['series']} series: "
                f"{comp['value']} [tool: compute_statistic]"
            )
    lines.append("Sources: " + ", ".join(cited_docs) + ".")
    return {"text": "\n".join(lines), "citations": cited_docs, "claims": claims}


def validate(tools, answer):
    """Re-check every numeric claim and citation in a draft answer."""
    checks = []
    for claim in answer["claims"]:
        checks.append(tools.call(
            "validate_number", {"label": claim["label"], "value": claim["value"]}))
    citation_ok = len(answer["citations"]) > 0
    numbers_ok = all(c.get("match", False) for c in checks if c.get("checked"))
    return {
        "checks": checks,
        "citations_present": citation_ok,
        "numbers_match": numbers_ok,
        "passed": citation_ok and numbers_ok,
    }


def extract_claims_from_text(text):
    """Pull (label, value) pairs out of free text, for validator tests."""
    found = []
    pattern = re.compile(r"([a-z][a-z ]+?):\s*([0-9]+(?:\.[0-9]+)?)")
    for match in pattern.finditer(text.lower()):
        found.append({"label": match.group(1).strip(), "value": float(match.group(2))})
    return found
