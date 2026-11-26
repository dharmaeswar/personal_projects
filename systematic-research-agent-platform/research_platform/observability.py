"""Observability: JSONL run log for every research run."""

import json


def log_run(path, result):
    """Append one run record (question, tools, validation) to a JSONL log."""
    record = {
        "question": result["question"],
        "tools_used": result["tools_used"],
        "citations": result["answer"]["citations"],
        "validation_passed": (
            result["validation"]["passed"] if result["validation"] else None
        ),
        "steps_used": result["steps_used"],
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record
