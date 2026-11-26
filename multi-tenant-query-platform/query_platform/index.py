"""Inverted index for full-text search plus per-field value indexes.

This is the Elasticsearch-shaped half of the platform: tokenize string
fields into terms, keep a term -> doc-id posting list, and keep exact-match
indexes for field values so filters run without scanning every document.
The index is built incrementally as documents are ingested and is scoped
per (tenant, collection) so one tenant's terms never leak into another's.
"""

from __future__ import annotations

import re
from collections import defaultdict

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class InvertedIndex:
    def __init__(self):
        # (tenant, collection, term) -> set of doc ids
        self._postings: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        # (tenant, collection, field, value-as-string) -> set of doc ids
        self._field_index: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
        # doc key -> terms, so a document can be removed/re-indexed cleanly
        self._doc_terms: dict[tuple[str, str, str], set[str]] = {}
        self._doc_fields: dict[tuple[str, str, str], set[tuple[str, str]]] = {}

    def index_document(self, tenant: str, collection: str, doc_id: str,
                       fields: dict, indexed_fields: set[str] | None = None) -> None:
        key = (tenant, collection, doc_id)
        self.remove_document(tenant, collection, doc_id)
        terms: set[str] = set()
        for name, value in fields.items():
            if indexed_fields is not None and name not in indexed_fields:
                continue
            if isinstance(value, str):
                for term in tokenize(value):
                    terms.add(term)
                    self._postings[(tenant, collection, term)].add(doc_id)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        for term in tokenize(item):
                            terms.add(term)
                            self._postings[(tenant, collection, term)].add(doc_id)
            # exact-match field index for scalars and lists
            vals = value if isinstance(value, list) else [value]
            fkeys = set()
            for v in vals:
                fkey = (tenant, collection, name, json_value(v))
                self._field_index[fkey].add(doc_id)
                fkeys.add((name, json_value(v)))
            self._doc_fields.setdefault(key, set()).update(fkeys)
        self._doc_terms[key] = terms

    def remove_document(self, tenant: str, collection: str, doc_id: str) -> None:
        key = (tenant, collection, doc_id)
        for term in self._doc_terms.pop(key, set()):
            self._postings[(tenant, collection, term)].discard(doc_id)
        for (name, val) in self._doc_fields.pop(key, set()):
            self._field_index[(tenant, collection, name, val)].discard(doc_id)

    def search_terms(self, tenant: str, collection: str, terms: list[str]) -> set[str]:
        """AND over terms: docs containing every term."""
        result: set[str] | None = None
        for term in terms:
            posting = self._postings.get((tenant, collection, term.lower()), set())
            result = set(posting) if result is None else result & posting
            if not result:
                return set()
        return result or set()

    def field_match(self, tenant: str, collection: str, field: str, value) -> set[str]:
        return set(self._field_index.get((tenant, collection, field, json_value(value)), set()))

    def terms_for(self, tenant: str, collection: str) -> int:
        return sum(1 for (t, c, _) in self._postings if t == tenant and c == collection)


def json_value(value) -> str:
    if isinstance(value, bool):
        return f"bool:{value}"
    if isinstance(value, (int, float)):
        return f"num:{value}"
    return f"str:{value}"
