import pytest

from query_platform.index import InvertedIndex
from query_platform.query import QueryEngine
from query_platform.store import DocumentStore


def _engine():
    store = DocumentStore()
    index = InvertedIndex()
    docs = [
        ("d1", {"title": "alpha report", "status": "approved", "amount": 100}),
        ("d2", {"title": "beta report", "status": "draft", "amount": 50}),
        ("d3", {"title": "alpha summary", "status": "approved", "amount": 200}),
    ]
    for doc_id, fields in docs:
        store.insert("t", "c", doc_id, 1, fields)
        index.index_document("t", "c", doc_id, fields)
    return QueryEngine(store, index)


def test_filter_eq_and_range():
    eng = _engine()
    r = eng.execute("t", "c", {"filter": {"status": "approved"}})
    assert r["total"] == 2
    r = eng.execute("t", "c", {"filter": {"amount": {"$gte": 100, "$lt": 200}}})
    assert [d["_id"] for d in r["documents"]] == ["d1"]


def test_filter_in_ne_and_unknown_operator():
    eng = _engine()
    r = eng.execute("t", "c", {"filter": {"status": {"$in": ["draft", "approved"]}}})
    assert r["total"] == 3
    r = eng.execute("t", "c", {"filter": {"status": {"$ne": "draft"}}})
    assert r["total"] == 2
    with pytest.raises(ValueError):
        eng.execute("t", "c", {"filter": {"amount": {"$near": 5}}})


def test_search_sort_and_pagination():
    eng = _engine()
    r = eng.execute("t", "c", {"search": "alpha", "sort": [("amount", "desc")]})
    assert [d["_id"] for d in r["documents"]] == ["d3", "d1"]
    r = eng.execute("t", "c", {"sort": [("amount", "asc")], "limit": 1, "offset": 1})
    assert r["total"] == 3 and [d["_id"] for d in r["documents"]] == ["d1"]


def test_aggregations():
    eng = _engine()
    r = eng.execute("t", "c", {"filter": {"status": "approved"}, "aggregate": {
        "count": True, "sum": {"total": "amount"}, "avg": {"avg": "amount"},
        "group_by": {"by_status": "status"}}})
    agg = r["aggregations"]
    assert agg["count"] == 2 and agg["total"] == 300 and agg["avg"] == 150
    assert agg["by_status"] == {"approved": 2}
