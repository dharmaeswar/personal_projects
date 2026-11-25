"""JSONL observability log for research-assistant queries."""

import json


def log_query(log_path, question, retrieved_ids, grounded, guardrail_passed, latency_ms):
    record = {
        "question": question,
        "retrieved_ids": retrieved_ids,
        "grounded": grounded,
        "guardrail_passed": guardrail_passed,
        "latency_ms": latency_ms,
    }
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
