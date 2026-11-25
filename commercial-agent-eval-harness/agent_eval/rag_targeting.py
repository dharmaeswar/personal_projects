"""Cash Equities client targeting and RAG evaluation (added Nov 25, 2026).

Extends the commercial agent eval harness for a Quantitative Trading &
Research — Cash Equities fit: a deterministic "who to call" ranker over
synthetic client-flow data (trades, axes, IOIs, trade ideas, market
events) and an evaluation layer for LLM-generated client content —
grounding each claim against retrieved sources, scoring prompt variants
by groundedness, and flagging hallucinated content.

All data is synthetic and seeded. No real clients, flows, axes or IOIs.
Nothing here is a claim about any real firm, desk or live return. The
ranker and the RAG judge are deterministic rule-based stand-ins, so every
eval is reproducible with no model API calls.
"""

from __future__ import annotations

import random

# Score weights: flow 35%, liquidity (axes + IOIs) 25%, idea match 25%,
# near-term market event 15%. They sum to 1.0 by construction.
WEIGHTS = {"flow": 0.35, "liquidity": 0.25, "idea_match": 0.25, "event": 0.15}

# Liquidity signal saturates at this many axes + IOIs combined.
LIQUIDITY_CAP = 12


def build_client_flow(seed=25):
    """Seeded synthetic client-flow snapshot: 12 fictional clients.

    Fields per client: client_id, name, sector, flow_usd_m (trailing-30-day
    traded volume), axes (open axe count), iois (indications of interest),
    idea_match (0-1 fit of the current trade idea to the client), event
    (a near-term catalyst such as earnings), last_contact_days.
    """
    rng = random.Random(seed)
    names = [
        ("C001", "Meridian Pension", "Industrials"),
        ("C002", "Atlas Asset Management", "Technology"),
        ("C003", "Beacon Hill Capital", "Financials"),
        ("C004", "Copperfield Endowment", "Healthcare"),
        ("C005", "Northgate Insurance", "Financials"),
        ("C006", "Harborview Funds", "Consumer"),
        ("C007", "Summit Ridge Advisors", "Technology"),
        ("C008", "Clearwater Foundation", "Energy"),
        ("C009", "Ironbridge Partners", "Industrials"),
        ("C010", "Westfield Mutual", "Healthcare"),
        ("C011", "Kingsway Investments", "Consumer"),
        ("C012", "Tidepool Family Office", "Energy"),
    ]
    clients = []
    for client_id, name, sector in names:
        clients.append({
            "client_id": client_id,
            "name": name,
            "sector": sector,
            "flow_usd_m": round(rng.uniform(2.0, 48.0), 1),
            "axes": rng.randint(0, 8),
            "iois": rng.randint(0, 6),
            "idea_match": round(rng.uniform(0.1, 0.95), 2),
            "event": rng.random() < 0.35,
            "last_contact_days": rng.randint(1, 45),
        })
    return clients


def score_client(client, max_flow):
    """Score one client 0-100 and explain the score.

    Returns (score, rationale): rationale is a list of plain-language
    reasons, one per contributing signal, so a salesperson can see why
    this client ranks where it does.
    """
    if max_flow <= 0:
        raise ValueError("max_flow must be positive")
    flow_norm = min(max(client["flow_usd_m"], 0.0) / max_flow, 1.0)
    liquidity_norm = min((client["axes"] + client["iois"]) / LIQUIDITY_CAP, 1.0)
    idea = min(max(client["idea_match"], 0.0), 1.0)
    event = 1.0 if client["event"] else 0.0
    score = 100.0 * (
        WEIGHTS["flow"] * flow_norm
        + WEIGHTS["liquidity"] * liquidity_norm
        + WEIGHTS["idea_match"] * idea
        + WEIGHTS["event"] * event
    )
    rationale = [
        f"flow ${client['flow_usd_m']:.1f}m ({flow_norm:.0%} of largest client)",
        f"liquidity: {client['axes']} axes + {client['iois']} IOIs",
        f"trade-idea match {idea:.0%}",
    ]
    if client["event"]:
        rationale.append("near-term catalyst this week")
    else:
        rationale.append("no near-term catalyst")
    if client["last_contact_days"] > 30:
        rationale.append(f"not contacted in {client['last_contact_days']} days")
    return round(score, 2), rationale


def rank_clients(clients):
    """Rank clients best-first by score. Returns ranked dicts with rank."""
    if not clients:
        return []
    max_flow = max(c["flow_usd_m"] for c in clients)
    ranked = []
    for client in clients:
        score, rationale = score_client(client, max_flow)
        ranked.append({
            "client_id": client["client_id"],
            "name": client["name"],
            "sector": client["sector"],
            "score": score,
            "rationale": rationale,
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    for i, entry in enumerate(ranked, start=1):
        entry["rank"] = i
    return ranked


def evaluate_draft(claims, sources):
    """Judge LLM-generated client content claim by claim.

    claims: list of {"text": str, "source_id": str, "keywords": [str]}.
    sources: {source_id: source text}. A claim is "supported" only when
    every keyword appears in the cited source text; "unsupported" when
    the source exists but a keyword is missing; "missing_source" when
    the cited source does not exist. Returns per-claim verdicts, the
    groundedness rate (supported / total; 1.0 when there are no claims)
    and a hallucination flag.
    """
    verdicts = []
    supported = 0
    for claim in claims:
        source_id = claim.get("source_id", "")
        keywords = [k.lower() for k in claim.get("keywords", [])]
        if source_id not in sources:
            verdict = "missing_source"
        else:
            text = sources[source_id].lower()
            verdict = ("supported" if all(k in text for k in keywords)
                       else "unsupported")
        if verdict == "supported":
            supported += 1
        verdicts.append({
            "text": claim.get("text", ""),
            "source_id": source_id,
            "verdict": verdict,
        })
    total = len(claims)
    groundedness = round(supported / total, 4) if total else 1.0
    return {
        "claims": verdicts,
        "total": total,
        "supported": supported,
        "groundedness": groundedness,
        "hallucinated": any(v["verdict"] != "supported" for v in verdicts),
    }


def compare_prompt_variants(variants):
    """Score prompt variants by the groundedness of their drafts.

    variants: list of {"name": str, "claims": [...], "sources": {...}}.
    Returns per-variant groundedness plus the best variant name (first
    variant wins a tie, so results are deterministic).
    """
    scored = []
    for variant in variants:
        result = evaluate_draft(variant["claims"], variant["sources"])
        scored.append({
            "name": variant["name"],
            "groundedness": result["groundedness"],
            "supported": result["supported"],
            "total": result["total"],
            "hallucinated": result["hallucinated"],
        })
    best = max(scored, key=lambda s: s["groundedness"]) if scored else None
    return {"variants": scored,
            "best": best["name"] if best else None}


# --- demo fixtures: one grounded draft and one loose draft -------------------

SOURCES = {
    "flow-001": ("Meridian Pension traded $42m in industrials this month, "
                 "up from $18m last month, with 3 block trades."),
    "axes-001": ("The desk shows axes in 6 industrial names totalling $25m, "
                 "including 2 blocks over $5m."),
}

GROUNDED_CLAIMS = [
    {"text": "Meridian traded $42m in industrials this month.",
     "source_id": "flow-001", "keywords": ["42m", "industrials"]},
    {"text": "Flow rose from $18m last month.",
     "source_id": "flow-001", "keywords": ["18m"]},
    {"text": "The desk shows axes in 6 industrial names totalling $25m.",
     "source_id": "axes-001", "keywords": ["6 industrial", "25m"]},
]

LOOSE_CLAIMS = GROUNDED_CLAIMS + [
    {"text": "Meridian also traded $90m in technology names.",
     "source_id": "flow-001", "keywords": ["90m", "technology"]},
]


def run_cash_equities_eval():
    """Run the targeting ranker and the RAG prompt comparison end to end."""
    clients = build_client_flow()
    ranked = rank_clients(clients)
    comparison = compare_prompt_variants([
        {"name": "grounded-prompt", "claims": GROUNDED_CLAIMS,
         "sources": SOURCES},
        {"name": "loose-prompt", "claims": LOOSE_CLAIMS,
         "sources": SOURCES},
    ])
    grounded = comparison["variants"][0]
    loose = comparison["variants"][1]
    verdict = ("PASS" if grounded["groundedness"] >= 0.9
               and ranked[0]["score"] >= 50
               and loose["hallucinated"] else "FAIL")
    return {
        "verdict": verdict,
        "top_clients": ranked[:5],
        "ranked_count": len(ranked),
        "prompt_comparison": comparison,
    }


def render_cash_equities_report(result):
    lines = [f"Cash Equities targeting + RAG eval: {result['verdict']}",
             "",
             "Top 5 clients to call:"]
    for entry in result["top_clients"]:
        lines.append(f"  {entry['rank']}. {entry['name']} "
                     f"({entry['sector']}) — score {entry['score']:.1f}")
        lines.append("     " + "; ".join(entry["rationale"]))
    lines.append("")
    lines.append("Prompt variants (groundedness):")
    for variant in result["prompt_comparison"]["variants"]:
        lines.append(f"  {variant['name']}: {variant['groundedness']:.2f} "
                     f"({variant['supported']}/{variant['total']} claims "
                     f"supported, hallucinated={variant['hallucinated']})")
    lines.append(f"Best variant: {result['prompt_comparison']['best']}")
    return "\n".join(lines) + "\n"
