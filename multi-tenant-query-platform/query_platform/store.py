"""Document store: per-tenant, per-collection documents with idempotent ingest.

Each document has an id, a tenant, a collection, the schema version it was
validated against, and its fields. Ingest is idempotent on (tenant,
collection, doc id): re-ingesting the same id with the same content is a
no-op, and re-ingesting with different content is rejected unless the
caller explicitly upserts. This mirrors the at-least-once delivery reality
of a streaming ingest path (Kafka/PubSub): retries must not duplicate rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Document:
    tenant: str
    collection: str
    doc_id: str
    schema_version: int
    fields: dict
    seq: int = 0  # ingest sequence number, assigned by the store


class DocumentStore:
    def __init__(self):
        self._docs: dict[tuple[str, str, str], Document] = {}
        self._seq = 0

    def insert(self, tenant: str, collection: str, doc_id: str,
               schema_version: int, fields: dict, upsert: bool = False) -> tuple[Document, bool]:
        """Insert a document. Returns (document, created?). Idempotent re-insert
        of identical content returns the existing document with created=False.
        Conflicting content without upsert raises ValueError."""
        key = (tenant, collection, doc_id)
        existing = self._docs.get(key)
        if existing is not None:
            if existing.fields == fields and existing.schema_version == schema_version:
                return existing, False
            if not upsert:
                raise ValueError(
                    f"document {doc_id!r} already exists with different content; pass upsert=True")
            self._seq += 1
            doc = Document(tenant, collection, doc_id, schema_version, dict(fields), self._seq)
            self._docs[key] = doc
            return doc, False
        self._seq += 1
        doc = Document(tenant, collection, doc_id, schema_version, dict(fields), self._seq)
        self._docs[key] = doc
        return doc, True

    def get(self, tenant: str, collection: str, doc_id: str) -> Document | None:
        return self._docs.get((tenant, collection, doc_id))

    def all(self, tenant: str, collection: str) -> list[Document]:
        return [d for (t, c, _), d in self._docs.items() if t == tenant and c == collection]

    def count(self, tenant: str, collection: str) -> int:
        return sum(1 for (t, c, _) in self._docs if t == tenant and c == collection)

    def to_json(self) -> str:
        docs = [vars(d) for d in self._docs.values()]
        return json.dumps({"documents": docs}, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "DocumentStore":
        store = cls()
        for raw in json.loads(text)["documents"]:
            doc = Document(**raw)
            store._docs[(doc.tenant, doc.collection, doc.doc_id)] = doc
            store._seq = max(store._seq, doc.seq)
        return store
