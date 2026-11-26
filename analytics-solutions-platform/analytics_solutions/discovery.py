"""Data-product discovery: help teams find and use business information.

This is the "front door" of the internal data product: business users ask
a question in plain words ("which policies are active, how much premium
do they carry?") and the service answers with the governed dataset that
answers it, its owner, its freshness and its quality score — instead of
users guessing which raw feed or dashboard to trust.

A product is a dict with:
  product_id, name, domain, owner, description, keywords (list),
  source_datasets (list), freshness_sla_hours, quality_score (0-100),
  contains_pii (bool), status ("live" | "deprecated" | "draft").

The catalog is a plain list of product dicts; nothing here calls a
network service. Freshness is computed from a caller-supplied
``last_refresh`` timestamp so tests stay deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

REQUIRED_FIELDS = (
    "product_id",
    "name",
    "domain",
    "owner",
    "description",
    "source_datasets",
    "freshness_sla_hours",
    "quality_score",
)


class CatalogError(ValueError):
    pass


def register_product(catalog: list[dict], product: dict) -> dict:
    """Validate and add a product to the catalog. Returns the stored copy."""
    for field in REQUIRED_FIELDS:
        if field not in product or product[field] in (None, ""):
            raise CatalogError(f"product missing required field: {field}")
    product_id = str(product["product_id"]).strip()
    if any(str(p["product_id"]) == product_id for p in catalog):
        raise CatalogError(f"duplicate product_id: {product_id}")
    if not isinstance(product["source_datasets"], list) or not product["source_datasets"]:
        raise CatalogError("source_datasets must be a non-empty list")
    score = product["quality_score"]
    if not isinstance(score, (int, float)) or not 0 <= score <= 100:
        raise CatalogError("quality_score must be a number between 0 and 100")
    if product["freshness_sla_hours"] <= 0:
        raise CatalogError("freshness_sla_hours must be positive")
    stored = dict(product)
    stored["product_id"] = product_id
    stored.setdefault("keywords", [])
    stored.setdefault("contains_pii", False)
    stored.setdefault("status", "live")
    catalog.append(stored)
    return stored


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().replace(",", " ").split() if t}


def _match_score(product: dict, query_tokens: set[str]) -> int:
    """Score a product against query tokens: name hits count double."""
    name_tokens = _tokens(str(product.get("name", "")))
    desc_tokens = _tokens(str(product.get("description", "")))
    keyword_tokens = {str(k).lower() for k in product.get("keywords", [])}
    score = 0
    for tok in query_tokens:
        if tok in name_tokens:
            score += 2
        if tok in desc_tokens or tok in keyword_tokens:
            score += 1
    return score


def search_products(catalog: list[dict], query: str, domain: str | None = None,
                    min_quality: float | None = None) -> list[dict]:
    """Rank live products matching the query. Empty query lists everything.

    Results are sorted by match score, then quality score. Deprecated and
    draft products never surface in search results.
    """
    query_tokens = _tokens(query or "")
    results: list[tuple[int, dict]] = []
    for product in catalog:
        if product.get("status") != "live":
            continue
        if domain and str(product.get("domain", "")).lower() != domain.lower():
            continue
        if min_quality is not None and product["quality_score"] < min_quality:
            continue
        score = _match_score(product, query_tokens) if query_tokens else 1
        if query_tokens and score == 0:
            continue
        results.append((score, product))
    results.sort(key=lambda item: (item[0], item[1]["quality_score"]), reverse=True)
    return [product for _, product in results]


def freshness_status(product: dict, last_refresh: datetime,
                     now: datetime) -> dict:
    """Is the product fresh against its SLA? Returns status + age in hours."""
    age_hours = (now - last_refresh).total_seconds() / 3600.0
    sla = float(product["freshness_sla_hours"])
    status = "fresh" if age_hours <= sla else "stale"
    return {
        "product_id": product["product_id"],
        "status": status,
        "age_hours": round(age_hours, 2),
        "sla_hours": sla,
    }


def answer_question(catalog: list[dict], question: str) -> dict:
    """Recommend the best product for a plain-words business question.

    Returns the top match plus the runner-up, each with the reason it was
    picked (matched terms) and a freshness reminder. No match returns an
    explicit empty answer instead of guessing.
    """
    matches = search_products(catalog, question)
    if not matches:
        return {"question": question, "answer": None,
                "reason": "no live product matches this question",
                "alternatives": []}
    top = matches[0]
    matched = sorted(_tokens(question) & (
        _tokens(top["name"]) | _tokens(top["description"])
        | {str(k).lower() for k in top.get("keywords", [])}))
    return {
        "question": question,
        "answer": top["product_id"],
        "reason": f"matches terms: {', '.join(matched)}; "
                  f"quality {top['quality_score']}/100; owner {top['owner']}",
        "alternatives": [p["product_id"] for p in matches[1:3]],
    }


def list_by_domain(catalog: list[dict]) -> dict[str, list[str]]:
    """Live products grouped by domain, highest quality first."""
    grouped: dict[str, list[str]] = {}
    for product in sorted(
            (p for p in catalog if p.get("status") == "live"),
            key=lambda p: p["quality_score"], reverse=True):
        grouped.setdefault(str(product["domain"]), []).append(str(product["product_id"]))
    return grouped


def product_card(product: dict, last_refresh: datetime | None = None,
                 now: datetime | None = None) -> dict:
    """One-dict summary a UI or API can render for a product."""
    card = {
        "product_id": product["product_id"],
        "name": product["name"],
        "domain": product["domain"],
        "owner": product["owner"],
        "description": product["description"],
        "quality_score": product["quality_score"],
        "contains_pii": bool(product.get("contains_pii", False)),
        "status": product.get("status", "live"),
        "sources": list(product["source_datasets"]),
    }
    if last_refresh is not None and now is not None:
        card["freshness"] = freshness_status(product, last_refresh, now)["status"]
    return card
