"""Retrieval API for the AI platform knowledge service.

A thin, testable service layer over the ingestion pipeline and the
vector store: ingest documents once, then answer retrieval queries
with ranked chunks, citations (doc id, chunk id, source) and a trace
id per request. Requests are wrapped in telemetry spans so latency
and failures are observable end to end.

Auth is a simple API-key check on the service object — the shape a
real gateway enforces with OAuth 2.0 / OIDC / Okta in front of the
service. This project never claims production auth: the key check
here is a local stand-in, and the key is passed in by the caller,
never read from a credential store.
"""

import uuid

from .ingestion import KnowledgeIngestionPipeline
from .observability import Telemetry
from .vector_store import VectorStore


class KnowledgeRetrievalAPI:
    """Ingest documents, then serve ranked retrieval with citations."""

    def __init__(self, store=None, telemetry=None, api_key=None):
        self.store = store if store is not None else VectorStore()
        self.telemetry = telemetry if telemetry is not None else Telemetry()
        self.api_key = api_key
        self._pipeline = KnowledgeIngestionPipeline(
            store=self.store, telemetry=self.telemetry
        )

    def ingest_documents(self, docs, strategy="sentence"):
        """Ingest ``docs`` with ``strategy``; returns the ingest report."""
        if strategy not in ("fixed", "sentence", "sliding"):
            raise ValueError(f"unknown strategy: {strategy}")
        self._pipeline.strategy = strategy
        return self._pipeline.ingest(docs)

    def retrieve(self, query, k=3, api_key=None):
        """Top-``k`` chunks for ``query`` with citations and a trace id."""
        if self.api_key is not None and api_key != self.api_key:
            raise PermissionError("invalid or missing API key")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        trace_id = uuid.uuid4().hex
        span = self.telemetry.start_span(
            "api.retrieve", {"trace_id": trace_id, "k": k}
        )
        vocab, idf = self.store.rebuild_index()
        hits = self.store.search(query, vocab, idf, k=k)
        results = [
            {
                "doc_id": chunk["doc_id"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "score": round(score, 4),
                "citation": f"{chunk['doc_id']}#chunk-{chunk['chunk_id']}",
            }
            for chunk, score in hits
        ]
        self.telemetry.end_span(
            span, status="ok" if results else "empty"
        )
        self.telemetry.increment("queries_served")
        return {
            "query": query,
            "trace_id": trace_id,
            "results": results,
        }

    def health(self):
        """Service health: status plus how many chunks are indexed."""
        return {"status": "ok", "chunks": len(self.store)}
