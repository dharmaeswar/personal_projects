"""Schema validation, dead-letter queue and offset checkpointing.

Streaming infrastructure needs three guarantees this module adds on
top of the plain consumer pipeline:

- **Validation**: every record is checked against the expected signal
  schema before it is scored. Malformed records go to a dead-letter
  queue (DLQ) with a reason instead of crashing the consumer or
  poisoning the store.
- **Exactly-once**: processed record keys (partition, offset) are
  remembered, so a redelivered record after a restart is skipped
  instead of scored and stored twice.
- **Checkpointing**: the consumer's committed offsets can be saved as
  a snapshot and restored after a restart, so processing resumes
  where it stopped instead of replaying the whole topic.
"""

from __future__ import annotations

REQUIRED_FIELDS = ("source_id", "event_type", "text")
NUMERIC_FIELDS = ("reliability", "keyword_severity", "corroborations", "age_seconds")


def validate_signal(signal: object) -> list[str]:
    """Return a list of validation problems; empty means the signal is valid."""
    problems: list[str] = []
    if not isinstance(signal, dict):
        return ["signal is not an object"]
    for name in REQUIRED_FIELDS:
        value = signal.get(name)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{name} must be a non-empty string")
    for name in NUMERIC_FIELDS:
        value = signal.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{name} must be a number")
    reliability = signal.get("reliability", 0.5)
    if isinstance(reliability, (int, float)) and not isinstance(reliability, bool):
        if not 0.0 <= reliability <= 1.0:
            problems.append("reliability must be in [0, 1]")
    keyword_severity = signal.get("keyword_severity", 0.5)
    if isinstance(keyword_severity, (int, float)) and not isinstance(keyword_severity, bool):
        if not 0.0 <= keyword_severity <= 1.0:
            problems.append("keyword_severity must be in [0, 1]")
    age = signal.get("age_seconds", 0.0)
    if isinstance(age, (int, float)) and not isinstance(age, bool) and age < 0:
        problems.append("age_seconds must be >= 0")
    corroborations = signal.get("corroborations", 0)
    if isinstance(corroborations, (int, float)) and not isinstance(corroborations, bool):
        if corroborations < 0:
            problems.append("corroborations must be >= 0")
    return problems


class DeadLetterQueue:
    """In-memory DLQ: malformed records kept with their failure reason."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def add(self, partition: int, offset: int, signal: object, problems: list[str]) -> None:
        self._entries.append(
            {
                "partition": partition,
                "offset": offset,
                "signal": signal,
                "problems": list(problems),
            }
        )

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[dict]:
        return list(self._entries)


class CheckpointStore:
    """Exactly-once bookkeeping plus offset snapshots for one consumer group."""

    def __init__(self) -> None:
        self._seen: set[tuple[int, int]] = set()
        self._offsets: dict[int, int] = {}

    def already_processed(self, partition: int, offset: int) -> bool:
        return (partition, offset) in self._seen

    def mark_processed(self, partition: int, offset: int) -> None:
        self._seen.add((partition, offset))
        self._offsets[partition] = max(self._offsets.get(partition, 0), offset + 1)

    def snapshot(self) -> dict:
        """Offsets to persist so a restart can resume without replay."""
        return {"offsets": dict(self._offsets), "processed": len(self._seen)}

    def restore(self, snapshot: dict) -> None:
        offsets = snapshot.get("offsets", {})
        if not isinstance(offsets, dict):
            raise ValueError("snapshot offsets must be a mapping")
        self._offsets = {int(p): int(o) for p, o in offsets.items()}
        self._seen = set()

    @property
    def offsets(self) -> dict[int, int]:
        return dict(self._offsets)
