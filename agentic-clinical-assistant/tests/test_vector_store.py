"""Tests for the vector store and feature store."""

from clinical_agent.vector_store import FeatureStore, VectorStore, cosine, embed


def test_embed_is_deterministic_and_unit_length():
    a = embed("diabetes follow-up care plan")
    b = embed("diabetes follow-up care plan")
    assert a == b
    assert abs(sum(v * v for v in a) - 1.0) < 1e-6


def test_cosine_identical_is_one():
    vector = embed("hypertension medication review")
    assert abs(cosine(vector, vector) - 1.0) < 1e-4


def test_vector_store_search_finds_matching_doc():
    store = VectorStore()
    store.upsert("d1", "diabetes follow-up care plan",
                 metadata={"patient_id": "P-1001"})
    store.upsert("d2", "broken arm cast removal instructions",
                 metadata={"patient_id": "P-1002"})
    results = store.search("diabetes follow-up")
    assert results and results[0][0]["doc_id"] == "d1"


def test_vector_store_metadata_filter():
    store = VectorStore()
    store.upsert("d1", "diabetes follow-up care plan",
                 metadata={"patient_id": "P-1001"})
    store.upsert("d2", "diabetes follow-up schedule",
                 metadata={"patient_id": "P-1002"})
    results = store.search("diabetes follow-up",
                           metadata_filter={"patient_id": "P-1002"})
    assert [r[0]["doc_id"] for r in results] == ["d2"]


def test_vector_store_upsert_rejects_empty():
    store = VectorStore()
    try:
        store.upsert("", "some text")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty doc_id")
    assert store.count() == 0


def test_vector_store_delete():
    store = VectorStore()
    store.upsert("d1", "diabetes follow-up care plan")
    assert store.delete("d1") is True
    assert store.delete("d1") is False
    assert store.count() == 0


def test_feature_store_versions():
    store = FeatureStore()
    store.put("P-1001", {"observation_count": 3}, "v1")
    store.put("P-1001", {"observation_count": 4}, "v2")
    assert store.get("P-1001", "v1") == {"observation_count": 3}
    assert store.get("P-1001") == {"observation_count": 4}
    assert store.versions("P-1001") == ["v1", "v2"]
    assert store.get("P-9999") is None
