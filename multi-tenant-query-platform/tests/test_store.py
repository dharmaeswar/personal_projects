import pytest

from query_platform.store import DocumentStore


def test_insert_and_idempotent_reinsert():
    store = DocumentStore()
    doc, created = store.insert("t", "c", "d1", 1, {"a": 1})
    assert created and doc.seq == 1
    doc2, created2 = store.insert("t", "c", "d1", 1, {"a": 1})
    assert not created2 and doc2.seq == 1
    assert store.count("t", "c") == 1


def test_conflicting_reinsert_rejected_without_upsert():
    store = DocumentStore()
    store.insert("t", "c", "d1", 1, {"a": 1})
    with pytest.raises(ValueError):
        store.insert("t", "c", "d1", 1, {"a": 2})
    doc, created = store.insert("t", "c", "d1", 2, {"a": 2}, upsert=True)
    assert not created and doc.fields == {"a": 2} and doc.schema_version == 2


def test_tenant_scoping_and_json_roundtrip():
    store = DocumentStore()
    store.insert("a", "c", "d1", 1, {"x": 1})
    store.insert("b", "c", "d1", 1, {"x": 2})
    assert store.count("a", "c") == 1 and store.count("b", "c") == 1
    assert store.get("a", "c", "d1").fields == {"x": 1}
    restored = DocumentStore.from_json(store.to_json())
    assert restored.get("b", "c", "d1").fields == {"x": 2}
    assert restored.count("a", "c") == 1
