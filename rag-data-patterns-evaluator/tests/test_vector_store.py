from rag_evaluator.corpus import DOCS
from rag_evaluator.chunking import chunk_corpus
from rag_evaluator.retrieval import build_index
from rag_evaluator.vector_store import VectorStore


def _filled_store():
    chunks = chunk_corpus(DOCS, "sentence")
    vocab, idf = build_index(chunks)
    store = VectorStore()
    store.upsert_chunks(chunks, vocab, idf)
    return store, vocab, idf, chunks


def test_search_ranks_relevant_doc_first():
    store, vocab, idf, _ = _filled_store()
    hits = store.search("Kafka streams usage events between billing systems", vocab, idf, k=3)
    assert hits[0][0]["doc_id"] == "kafka-streaming"
    assert hits[0][1] > 0
    scores = [score for _, score in hits]
    assert scores == sorted(scores, reverse=True)


def test_upsert_replaces_duplicate_chunk():
    store, vocab, idf, chunks = _filled_store()
    first = chunks[0]
    assert len(store) == len(chunks)
    store.add(first, {})
    assert len(store) == len(chunks)


def test_save_load_round_trip_preserves_search():
    store, vocab, idf, _ = _filled_store()
    path = "/tmp/rag_vector_store_test.json"
    store.save(path)
    loaded = VectorStore.load(path)
    assert len(loaded) == len(store)
    before = store.search("ETL pipelines extract data nightly", vocab, idf, k=3)
    after = loaded.search("ETL pipelines extract data nightly", vocab, idf, k=3)
    assert [c["doc_id"] for c, _ in before] == [c["doc_id"] for c, _ in after]


def test_empty_store_search_returns_nothing():
    store = VectorStore()
    vocab, idf = build_index([])
    assert store.search("anything", vocab, idf, k=3) == []
    assert len(store) == 0


def test_clear_empties_store():
    store, _, _, _ = _filled_store()
    assert len(store) > 0
    store.clear()
    assert len(store) == 0
