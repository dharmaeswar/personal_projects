"""In-memory vector store for embedded knowledge chunks.

Each chunk is stored with its sparse TF-IDF embedding (see
``retrieval.embed``) under the key ``(doc_id, chunk_id)``. The store
supports upsert (re-ingesting a chunk replaces its old vector), ranked
cosine search, and JSON save/load so an ingested knowledge base can be
reloaded without re-chunking. This is the local, deterministic stand-in
for the vector-search layer of an enterprise AI platform — no model
downloads, no cloud service, no credentials.
"""

import json
from pathlib import Path

from .retrieval import build_index, cosine, embed


class VectorStore:
    """Chunk embeddings keyed by (doc_id, chunk_id)."""

    def __init__(self):
        self._entries = {}

    def __len__(self):
        return len(self._entries)

    def add(self, chunk, vector):
        """Store one chunk with its embedding; replaces any prior entry."""
        key = (chunk["doc_id"], chunk["chunk_id"])
        self._entries[key] = {"chunk": dict(chunk), "vector": dict(vector)}

    def upsert_chunks(self, chunks, vocab, idf):
        """Embed every chunk and store it; returns the number stored."""
        for chunk in chunks:
            self.add(chunk, embed(chunk["text"], vocab, idf))
        return len(chunks)

    def chunks(self):
        """All stored chunks, in insertion order."""
        return [entry["chunk"] for entry in self._entries.values()]

    def search(self, query, vocab, idf, k=3):
        """Top-``k`` (chunk, score) pairs for ``query``, best first."""
        query_vec = embed(query, vocab, idf)
        scored = [
            (cosine(query_vec, entry["vector"]), i, entry["chunk"])
            for i, entry in enumerate(self._entries.values())
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(chunk, score) for score, _, chunk in scored[:k]]

    def rebuild_index(self):
        """Rebuild (vocab, idf) from the chunks currently stored."""
        return build_index(self.chunks())

    def save(self, path):
        """Write the store to ``path`` as JSON; returns the path."""
        data = [
            {
                "chunk": entry["chunk"],
                "vector": {str(col): w for col, w in entry["vector"].items()},
            }
            for entry in self._entries.values()
        ]
        Path(path).write_text(json.dumps(data, indent=2) + "\n")
        return str(path)

    @classmethod
    def load(cls, path):
        """Read a store written by :meth:`save`; returns a VectorStore."""
        store = cls()
        for item in json.loads(Path(path).read_text()):
            vector = {int(col): w for col, w in item["vector"].items()}
            store.add(item["chunk"], vector)
        return store

    def clear(self):
        """Remove every stored chunk."""
        self._entries.clear()
