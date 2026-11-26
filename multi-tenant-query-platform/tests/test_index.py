from query_platform.index import InvertedIndex, tokenize


def test_tokenize_lowercases_and_splits():
    assert tokenize("Master Services Agreement!") == ["master", "services", "agreement"]


def test_search_and_requires_all_terms():
    idx = InvertedIndex()
    idx.index_document("t", "c", "d1", {"title": "Master services agreement"})
    idx.index_document("t", "c", "d2", {"title": "Vendor agreement"})
    assert idx.search_terms("t", "c", ["agreement"]) == {"d1", "d2"}
    assert idx.search_terms("t", "c", ["master", "agreement"]) == {"d1"}
    assert idx.search_terms("t", "c", ["missing"]) == set()


def test_tenant_isolation_in_index():
    idx = InvertedIndex()
    idx.index_document("a", "c", "d1", {"title": "shared word"})
    idx.index_document("b", "c", "d1", {"title": "shared word"})
    assert idx.search_terms("a", "c", ["shared"]) == {"d1"}
    assert idx.search_terms("b", "c", ["shared"]) == {"d1"}
    assert idx.search_terms("a", "c", ["word"]) == {"d1"}


def test_field_match_and_remove():
    idx = InvertedIndex()
    idx.index_document("t", "c", "d1", {"status": "approved", "tags": ["a", "b"]})
    assert idx.field_match("t", "c", "status", "approved") == {"d1"}
    assert idx.field_match("t", "c", "tags", "b") == {"d1"}
    assert idx.field_match("t", "c", "status", "draft") == set()
    idx.remove_document("t", "c", "d1")
    assert idx.search_terms("t", "c", ["approved"]) == set()
    assert idx.field_match("t", "c", "status", "approved") == set()


def test_reindex_replaces_terms():
    idx = InvertedIndex()
    idx.index_document("t", "c", "d1", {"title": "old words"})
    idx.index_document("t", "c", "d1", {"title": "new words"})
    assert idx.search_terms("t", "c", ["old"]) == set()
    assert idx.search_terms("t", "c", ["new"]) == {"d1"}
