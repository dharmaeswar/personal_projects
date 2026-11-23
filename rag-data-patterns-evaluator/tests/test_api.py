import pytest

from rag_evaluator.api import KnowledgeRetrievalAPI
from rag_evaluator.corpus import DOCS


def _api_with_docs(api_key=None):
    api = KnowledgeRetrievalAPI(api_key=api_key)
    report = api.ingest_documents(DOCS)
    assert report["docs_accepted"] == len(DOCS)
    return api


def test_retrieve_returns_ranked_citations_with_trace_id():
    api = _api_with_docs()
    response = api.retrieve("Kafka streams usage events between billing systems", k=3)
    assert response["trace_id"]
    assert len(response["results"]) == 3
    assert response["results"][0]["doc_id"] == "kafka-streaming"
    for result in response["results"]:
        assert result["citation"].startswith(result["doc_id"] + "#chunk-")
        assert result["text"]
    scores = [result["score"] for result in response["results"]]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_empty_query_rejected():
    api = _api_with_docs()
    with pytest.raises(ValueError, match="non-empty string"):
        api.retrieve("   ")


def test_api_key_gate_blocks_wrong_key_and_allows_right_key():
    api = _api_with_docs(api_key="secret-key")
    with pytest.raises(PermissionError, match="API key"):
        api.retrieve("ETL pipelines", api_key="wrong-key")
    with pytest.raises(PermissionError, match="API key"):
        api.retrieve("ETL pipelines")
    response = api.retrieve("ETL pipelines", api_key="secret-key")
    assert response["results"]


def test_unknown_strategy_rejected():
    api = KnowledgeRetrievalAPI()
    with pytest.raises(ValueError, match="unknown strategy"):
        api.ingest_documents(DOCS, strategy="neural")


def test_health_reports_indexed_chunks():
    api = _api_with_docs()
    health = api.health()
    assert health["status"] == "ok"
    assert health["chunks"] > 0


def test_retrieve_records_telemetry():
    api = _api_with_docs()
    api.retrieve("data quality checks flag missing values", k=2)
    names = [span["name"] for span in api.telemetry.spans]
    assert "api.retrieve" in names
    assert api.telemetry.counters["queries_served"] == 1
