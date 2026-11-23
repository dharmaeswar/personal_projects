"""Knowledge-ingestion pipeline for the AI platform service.

Takes raw documents (``{"id", "text", "source"}``), validates them,
chunks them with one of the evaluator's strategies, embeds the chunks
and upserts them into a :class:`VectorStore`. Every stage records a
telemetry span, so a failed or slow ingestion can be traced stage by
stage — the same shape the platform's observability layer expects.

Bad documents are rejected with a plain reason and never reach the
store; a bad document never fails the whole batch.
"""

from .chunking import STRATEGIES, chunk_corpus
from .observability import Telemetry
from .retrieval import build_index
from .vector_store import VectorStore


def validate_document(doc):
    """Return a list of problems with ``doc``; empty means valid."""
    problems = []
    if not isinstance(doc, dict):
        return ["document is not an object"]
    if not isinstance(doc.get("id"), str) or not doc["id"].strip():
        problems.append("missing or empty id")
    if not isinstance(doc.get("text"), str) or not doc["text"].strip():
        problems.append("missing or empty text")
    if "source" in doc and not isinstance(doc["source"], str):
        problems.append("source is not a string")
    return problems


class KnowledgeIngestionPipeline:
    """Validate -> chunk -> embed -> upsert, with telemetry spans."""

    def __init__(self, store=None, telemetry=None, strategy="sentence"):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy: {strategy}")
        self.store = store if store is not None else VectorStore()
        self.telemetry = telemetry if telemetry is not None else Telemetry()
        self.strategy = strategy

    def ingest(self, docs):
        """Ingest ``docs``; return a report dict with counts and rejects."""
        report = {
            "strategy": self.strategy,
            "docs_seen": len(docs),
            "docs_accepted": 0,
            "docs_rejected": 0,
            "rejected": [],
            "chunks": 0,
        }
        span = self.telemetry.start_span(
            "ingest.validate", {"docs_seen": len(docs)}
        )
        accepted = []
        for doc in docs:
            problems = validate_document(doc)
            if problems:
                doc_id = doc.get("id") if isinstance(doc, dict) else None
                report["rejected"].append(
                    {"id": doc_id, "reasons": problems}
                )
                report["docs_rejected"] += 1
                self.telemetry.record_event(
                    "ingest.document_rejected",
                    {"id": str(doc_id), "reasons": "; ".join(problems)},
                )
            else:
                accepted.append(doc)
        self.telemetry.end_span(span)
        report["docs_accepted"] = len(accepted)

        span = self.telemetry.start_span(
            "ingest.chunk", {"strategy": self.strategy}
        )
        chunks = chunk_corpus(accepted, self.strategy)
        self.telemetry.end_span(span)

        span = self.telemetry.start_span(
            "ingest.embed_upsert", {"chunks": len(chunks)}
        )
        # Rebuild the index over old + new chunks so new embeddings share
        # one vocabulary with what is already stored.
        vocab, idf = build_index(self.store.chunks() + chunks)
        self.store.upsert_chunks(chunks, vocab, idf)
        self.telemetry.end_span(span)

        self.telemetry.increment("docs_ingested", len(accepted))
        self.telemetry.increment("chunks_ingested", len(chunks))
        report["chunks"] = len(chunks)
        report["store_chunks"] = len(self.store)
        return report
