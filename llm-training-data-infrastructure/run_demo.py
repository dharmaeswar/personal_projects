"""Seed a demo catalog (all synthetic) and print the dashboard summary.

Usage: python run_demo.py
"""
from llm_data_infra import ingestion, service
from llm_data_infra.store import Store


def seed(store: Store):
    text_ds = store.create_dataset(
        "webtext-v3", "text", "data-platform",
        "Web text corpus for pretraining, deduplicated and quality-gated.",
    )
    mm_ds = store.create_dataset(
        "image-text-pairs-v1", "multimodal", "data-platform",
        "Image-caption pairs for multimodal training.",
    )
    store.create_version(text_ds, "3.0")
    store.create_version(mm_ds, "1.0")
    batch = [
        {"text": "The quick brown fox jumps over the lazy dog near the riverbank.", "source": "web"},
        {"text": "The quick brown fox jumps over the lazy dog near the riverbank.", "source": "web"},  # duplicate
        {"text": "Short", "source": "web"},  # too short -> quarantine
        {"text": "Contact the team at help@example.com for details on the program.", "source": "web"},  # PII -> quarantine
        {"text": "Gradient descent updates model weights by stepping against the loss gradient each batch.", "source": "docs"},
        {"text": "Attention layers let each token weigh every other token in the sequence.", "source": "docs"},
    ]
    result = ingestion.ingest_batch(store, text_ds, "3.0", batch, "text")
    stream = (
        {"text": "A photo of a cat sitting on a windowsill in the afternoon sun.", "uri": "img://0001.jpg"}
        for _ in range(1)
    )
    stream_result = ingestion.ingest_stream(store, mm_ds, "1.0", stream, "multimodal")
    store.add_lineage(text_ds, "3.0", mm_ds, "1.0", "caption-join")
    return result, stream_result


if __name__ == "__main__":
    store = Store("llm_data_infra.db")
    batch, stream = seed(store)
    print("batch ingest:", batch)
    print("stream ingest:", stream)
    dash = service.dashboard(store)
    print("ingestion:", dash["ingestion"])
    print("pipeline health:", dash["pipeline_health"])
