"""Context engineering: pack retrieved evidence into a bounded context
window for the analyst agent.

Rules: numeric facts first (they ground every computed number), then
memo/covenant text; drop duplicate sentences; stop adding chunks once the
character budget is spent; every packed chunk keeps its doc_id citation.
"""

DEFAULT_BUDGET_CHARS = 1200


def _sentences(text):
    return [s.strip() for s in text.split(". ") if s.strip()]


def build_context(retrieved, budget_chars=DEFAULT_BUDGET_CHARS):
    """Pack retrieved chunks into a context dict.

    Returns {"chunks": [...], "chars_used": int, "truncated": bool,
    "citations": [doc_id, ...]}.
    """
    chunks = []
    seen_sentences = set()
    chars_used = 0
    truncated = False
    # Numeric facts first, then everything else, in retrieval order.
    ordered = sorted(retrieved, key=lambda r: 0 if r["source"] == "numeric-table" else 1)
    for item in ordered:
        for sentence in _sentences(item["text"]):
            sentence = sentence if sentence.endswith(".") else sentence + "."
            if sentence in seen_sentences:
                continue
            if chars_used + len(sentence) + 1 > budget_chars:
                truncated = True
                continue
            seen_sentences.add(sentence)
            chunks.append({"doc_id": item["doc_id"], "borrower": item["borrower"],
                           "kind": item["kind"], "text": sentence,
                           "source": item["source"]})
            chars_used += len(sentence) + 1
    return {
        "chunks": chunks,
        "chars_used": chars_used,
        "truncated": truncated,
        "citations": sorted({c["doc_id"] for c in chunks}),
    }


def context_text(context):
    """Render the packed context as the prompt block the analyst sees."""
    lines = []
    for chunk in context["chunks"]:
        lines.append(f"[{chunk['doc_id']}] {chunk['text']}")
    return "\n".join(lines)
