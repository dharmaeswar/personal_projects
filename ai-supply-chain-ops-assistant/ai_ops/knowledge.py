"""Knowledge discovery over seeded supply-chain operations runbooks.

Retrieval is deterministic keyword overlap (a stand-in for the embedding /
language-model retrieval the real product would call). Every answer cites
the runbook passage it came from, and the assistant abstains when no
passage matches well enough instead of inventing an answer.
"""

import re

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "what", "when", "where",
    "which", "who", "how", "do", "does", "did", "can", "could", "should",
    "would", "will", "for", "of", "to", "in", "on", "at", "by", "with",
    "and", "or", "if", "it", "its", "this", "that", "from", "as", "be",
    "i", "we", "you", "our", "my", "please", "tell", "me", "about",
}

# Seeded runbooks: id, title, passage. Synthetic demo content.
RUNBOOKS = [
    {
        "id": "RB-RECEIVING-01",
        "title": "Receiving a delivery at a fulfillment center",
        "text": (
            "When a delivery arrives, scan the carrier manifest first, then "
            "count cartons against the advance shipping notice. If the carton "
            "count differs by more than 2 percent, hold the shipment in the "
            "receiving bay and open a discrepancy ticket before putaway. "
            "Damaged cartons go to the quarantine cage with photos attached."
        ),
    },
    {
        "id": "RB-STOCKOUT-02",
        "title": "Handling a stockout on a fast-moving SKU",
        "text": (
            "When a fast-moving SKU hits zero on-hand stock, first check "
            "in-transit purchase orders and the transfer pool at nearby "
            "fulfillment centers. If no transfer covers the gap within 48 "
            "hours, raise a stockout alert to the buying team and mark the "
            "SKU as backorderable only if the supplier confirms a ship date."
        ),
    },
    {
        "id": "RB-REORDER-03",
        "title": "Reorder point and safety stock rules",
        "text": (
            "The reorder point equals average daily demand times lead time "
            "in days plus safety stock. Safety stock is set at 1.65 times "
            "the standard deviation of daily demand times the square root "
            "of lead time, which covers about 95 percent of demand "
            "variation. Review reorder points every Monday after the weekly "
            "demand forecast refresh."
        ),
    },
    {
        "id": "RB-CARRIER-04",
        "title": "Carrier delay and at-risk orders",
        "text": (
            "When a carrier reports a delay, list every order on that lane "
            "with a promised delivery date inside the delay window. Offer "
            "affected customers a new delivery estimate first; only reroute "
            "through another carrier when the delay exceeds 72 hours and "
            "the order value is above 75 dollars. Log the delay reason "
            "against each affected order."
        ),
    },
    {
        "id": "RB-RETURNS-05",
        "title": "Processing customer returns",
        "text": (
            "Returns are inspected within 24 hours of arrival. Resellable "
            "items return to available stock at the receiving center that "
            "took them in. Damaged or opened consumables are written off "
            "and never restocked. Refunds are issued only after inspection "
            "passes, and the refund reason code must match the inspection note."
        ),
    },
    {
        "id": "RB-TRANSFER-06",
        "title": "Transferring stock between fulfillment centers",
        "text": (
            "Transfers move stock from a center with more than 30 days of "
            "cover to one with less than 7 days of cover for the same SKU. "
            "The sending center confirms pick and pack within one business "
            "day, and the receiving center confirms receipt before the "
            "transfer closes. Never transfer the last unit of a SKU out of "
            "a center that serves same-day delivery."
        ),
    },
]

MIN_SCORE = 0.20


def _tokens(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS}


def retrieve(question, top_k=3):
    """Rank runbooks by token overlap with the question.

    Returns a list of (score, runbook) sorted best first, where score is
    the share of the question's content tokens found in the passage.
    """
    q_tokens = _tokens(question)
    if not q_tokens:
        return []
    scored = []
    for rb in RUNBOOKS:
        rb_tokens = _tokens(rb["text"]) | _tokens(rb["title"])
        overlap = len(q_tokens & rb_tokens)
        score = overlap / len(q_tokens)
        scored.append((score, rb))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top_k]


def answer(question):
    """Answer a knowledge question from the runbooks.

    Returns a dict with the answer text, cited sources, and whether the
    assistant abstained. Abstention is the safe behaviour when nothing in
    the knowledge base matches the question.
    """
    ranked = retrieve(question, top_k=3)
    if not ranked or ranked[0][0] < MIN_SCORE:
        return {
            "question": question,
            "answer": (
                "I don't know — nothing in the operations runbooks covers "
                "this question. Please ask the supply-chain team."
            ),
            "sources": [],
            "abstained": True,
            "score": ranked[0][0] if ranked else 0.0,
        }
    score, best = ranked[0]
    sources = [
        {"id": rb["id"], "title": rb["title"], "score": round(s, 3)}
        for s, rb in ranked
        if s >= MIN_SCORE
    ]
    return {
        "question": question,
        "answer": best["text"],
        "sources": sources,
        "abstained": False,
        "score": round(score, 3),
    }
