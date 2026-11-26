"""Deterministic in-memory vector store and feature store.

The CVS Health Sr SDE role calls for data pipelines, feature and vector
stores behind LLM-powered backend services. This module is the portfolio
stand-in for those stores: pure Python, no model downloads, no network.

Embeddings are deterministic hashed bag-of-words vectors, so indexing and
search are reproducible and testable without a real embedding model. The
README says so plainly — these are not production embeddings.
"""

import hashlib
import math

DIM = 64


def embed(text):
    """Deterministic hashed embedding: unit-length, DIM-dimensional."""
    vector = [0.0] * DIM
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


def cosine(a, b):
    """Cosine similarity of two equal-length vectors."""
    return round(sum(x * y for x, y in zip(a, b)), 6)


class VectorStore:
    """Small in-memory vector store with metadata filtering."""

    def __init__(self):
        self._records = {}

    def upsert(self, doc_id, text, metadata=None):
        if not doc_id or not text:
            raise ValueError("doc_id and text are required")
        self._records[doc_id] = {
            "doc_id": doc_id,
            "text": text,
            "vector": embed(text),
            "metadata": dict(metadata or {}),
        }
        return doc_id

    def delete(self, doc_id):
        return self._records.pop(doc_id, None) is not None

    def search(self, query, top_k=3, metadata_filter=None):
        """Top-k records by cosine similarity, honoring a metadata filter."""
        query_vector = embed(query)
        scored = []
        for record in self._records.values():
            meta = record["metadata"]
            if metadata_filter and any(
                meta.get(key) != value for key, value in metadata_filter.items()
            ):
                continue
            score = cosine(query_vector, record["vector"])
            if score > 0:
                scored.append((record, score))
        scored.sort(key=lambda pair: (-pair[1], pair[0]["doc_id"]))
        return scored[: max(1, top_k)]

    def count(self):
        return len(self._records)


class FeatureStore:
    """Versioned offline feature store for patient-level features.

    Each feature set is stored per entity with a version tag, so a model
    trained on v1 features can be reproduced even after v2 is published.
    """

    def __init__(self):
        self._features = {}

    def put(self, entity_id, features, version):
        if not entity_id or not isinstance(features, dict):
            raise ValueError("entity_id and a features dict are required")
        self._features.setdefault(entity_id, {})[version] = dict(features)
        return version

    def get(self, entity_id, version=None):
        versions = self._features.get(entity_id)
        if not versions:
            return None
        if version is None:
            version = sorted(versions)[-1]
        return dict(versions.get(version, {})) or None

    def versions(self, entity_id):
        return sorted(self._features.get(entity_id, {}))

    def entities(self):
        return sorted(self._features)
