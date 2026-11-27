"""Grounded answer composition: extractive stand-in for an LLM generator.

Every claim in the answer is a sentence copied from a retrieved passage,
carrying a citation to its source document. When no retrieved passage is
relevant, the composer abstains instead of inventing an answer. A real LLM
generator plugs into the same `answer(question, retrieved_docs)` shape;
its drafts would go through the same citation and groundedness checks.
"""

import re

from .graph import find_entities

_SENTENCE = re.compile(r"[^.]+\.")


def _sentences(text):
    return [s.strip() for s in _SENTENCE.findall(text)]


def answer(question, documents, doc_ids):
    """Compose a grounded answer from the retrieved documents.

    Returns {"answer": str, "claims": [{"text", "source"}],
    "abstained": bool}. A claim is grounded when its source document is
    one of the retrieved documents.
    """
    by_id = {d["id"]: d for d in documents}
    entities = find_entities(question)
    claims = []
    for doc_id in doc_ids:
        doc = by_id.get(doc_id)
        if doc is None:
            continue
        for sentence in _sentences(doc["text"]):
            mentioned = find_entities(sentence)
            if entities and not set(mentioned) & set(entities):
                continue
            claims.append({"text": sentence, "source": doc_id})
    if not claims:
        return {
            "answer": "Not covered by the documents: no retrieved passage mentions the entities in the question.",
            "claims": [],
            "abstained": True,
        }
    # Keep at most one claim per relation sentence, in retrieval order,
    # capped at four claims so the answer stays short and checkable.
    seen = set()
    picked = []
    for claim in claims:
        if claim["text"] not in seen:
            seen.add(claim["text"])
            picked.append(claim)
        if len(picked) == 4:
            break
    lines = [f"- {c['text']} [{c['source']}]" for c in picked]
    return {"answer": "\n".join(lines), "claims": picked, "abstained": False}


def groundedness(result, retrieved_ids):
    """Fraction of claims whose source is a retrieved document.

    1.0 means every claim is backed by retrieved evidence. An abstention
    has no claims and scores 1.0 by construction — it makes no claims.
    """
    claims = result["claims"]
    if not claims:
        return 1.0
    backed = sum(1 for c in claims if c["source"] in retrieved_ids)
    return backed / len(claims)
