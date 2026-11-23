import pytest

from rag_evaluator.corpus import DOCS
from rag_evaluator.ingestion import KnowledgeIngestionPipeline, validate_document


def test_validate_document_accepts_good_doc():
    assert validate_document({"id": "a", "text": "some text", "source": "wiki"}) == []


def test_validate_document_lists_each_problem():
    assert "missing or empty id" in validate_document({"text": "x"})
    assert "missing or empty text" in validate_document({"id": "a", "text": "  "})
    assert validate_document("not a dict") == ["document is not an object"]
    assert "source is not a string" in validate_document(
        {"id": "a", "text": "x", "source": 7}
    )


def test_ingest_accepts_valid_docs_and_reports_counts():
    pipeline = KnowledgeIngestionPipeline(strategy="sentence")
    report = pipeline.ingest(DOCS[:3])
    assert report["docs_seen"] == 3
    assert report["docs_accepted"] == 3
    assert report["docs_rejected"] == 0
    assert report["chunks"] > 0
    assert report["store_chunks"] == report["chunks"]
    assert len(pipeline.store) == report["chunks"]


def test_ingest_rejects_bad_docs_without_failing_batch():
    pipeline = KnowledgeIngestionPipeline(strategy="fixed")
    docs = [
        {"id": "good", "text": "ETL pipelines extract data nightly from source systems."},
        {"id": "", "text": "no id here"},
        {"id": "empty", "text": "   "},
        {"text": "no id at all"},
    ]
    report = pipeline.ingest(docs)
    assert report["docs_accepted"] == 1
    assert report["docs_rejected"] == 3
    assert len(report["rejected"]) == 3
    assert report["chunks"] > 0
    assert len(pipeline.store) == report["chunks"]


def test_ingest_records_telemetry_spans_and_counters():
    pipeline = KnowledgeIngestionPipeline(strategy="sliding")
    pipeline.ingest(DOCS[:2])
    names = {span["name"] for span in pipeline.telemetry.spans}
    assert names == {"ingest.validate", "ingest.chunk", "ingest.embed_upsert"}
    assert pipeline.telemetry.counters["docs_ingested"] == 2
    assert pipeline.telemetry.counters["chunks_ingested"] > 0


def test_unknown_strategy_rejected():
    with pytest.raises(ValueError, match="unknown strategy"):
        KnowledgeIngestionPipeline(strategy="neural")
