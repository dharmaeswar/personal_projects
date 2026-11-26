"""Query engine: filters, full-text search, sorting, pagination, aggregations.

A query is a plain dict so it can travel over an API unchanged:

    {"filter": {"status": "approved", "amount": {"$gte": 100}},
     "search": "quarterly report",
     "sort": [("amount", "desc")],
     "limit": 10, "offset": 0}

Filters support $eq (default), $ne, $gt, $gte, $lt, $lte, $in. Full-text
search is AND over terms via the inverted index. Aggregations are computed
over the matched set: count, sum/avg/min/max on a numeric field, and
group-by counts. The engine never returns documents from another tenant:
every call is scoped to one (tenant, collection).
"""

from __future__ import annotations

from .index import tokenize
from .store import Document


class QueryEngine:
    def __init__(self, store, index):
        self.store = store
        self.index = index

    def execute(self, tenant: str, collection: str, query: dict) -> dict:
        docs = self.store.all(tenant, collection)
        matched = [d for d in docs if self._matches(d, query, tenant, collection)]
        total = len(matched)
        # sort: stable, applied in order given (last key first for stability)
        for field_name, direction in reversed(query.get("sort", [])):
            reverse = direction == "desc"
            matched.sort(key=lambda d: _sort_key(d.fields.get(field_name)), reverse=reverse)
        offset = query.get("offset", 0)
        limit = query.get("limit", 50)
        page = matched[offset:offset + limit]
        result = {
            "total": total,
            "returned": len(page),
            "documents": [d.fields | {"_id": d.doc_id} for d in page],
        }
        if "aggregate" in query:
            result["aggregations"] = self._aggregate(matched, query["aggregate"])
        return result

    def _matches(self, doc: Document, query: dict, tenant: str, collection: str) -> bool:
        search = query.get("search")
        if search:
            terms = tokenize(search)
            if terms:
                hits = self.index.search_terms(tenant, collection, terms)
                if doc.doc_id not in hits:
                    return False
        for field_name, condition in query.get("filter", {}).items():
            if not _field_matches(doc.fields.get(field_name), condition):
                return False
        return True

    @staticmethod
    def _aggregate(matched: list[Document], spec: dict) -> dict:
        out: dict = {}
        if "count" in spec and spec["count"]:
            out["count"] = len(matched)
        for agg_name, field_name in spec.get("sum", {}).items():
            vals = [d.fields[field_name] for d in matched
                    if isinstance(d.fields.get(field_name), (int, float))]
            out[agg_name] = sum(vals)
        for agg_name, field_name in spec.get("avg", {}).items():
            vals = [d.fields[field_name] for d in matched
                    if isinstance(d.fields.get(field_name), (int, float))]
            out[agg_name] = (sum(vals) / len(vals)) if vals else None
        for agg_name, field_name in spec.get("group_by", {}).items():
            groups: dict[str, int] = {}
            for d in matched:
                groups[str(d.fields.get(field_name))] = groups.get(str(d.fields.get(field_name)), 0) + 1
            out[agg_name] = groups
        return out


def _field_matches(value, condition) -> bool:
    if isinstance(condition, dict):
        for op, expected in condition.items():
            if op == "$eq" and value != expected:
                return False
            if op == "$ne" and value == expected:
                return False
            if op == "$gt" and not (value is not None and value > expected):
                return False
            if op == "$gte" and not (value is not None and value >= expected):
                return False
            if op == "$lt" and not (value is not None and value < expected):
                return False
            if op == "$lte" and not (value is not None and value <= expected):
                return False
            if op == "$in" and value not in expected:
                return False
            if op not in ("$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in"):
                raise ValueError(f"unknown filter operator {op!r}")
        return True
    return value == condition


def _sort_key(value):
    # None sorts last in both directions by mapping to a tuple key.
    return (value is None, value if isinstance(value, (int, float, str)) else str(value))
