"""Provenance records for every agent-produced result.

Every result an agent obtains through the tool layer carries a provenance
record: which tool ran, which agent asked, a hash of the exact inputs, the
golden-reference version it was checked against, and a hash of the result.
A change with no provenance cannot land — reviewers can reproduce any
result from its record alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone


def _canonical_hash(payload: object) -> str:
    """SHA-256 of the canonical JSON form of a payload (stable key order)."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Provenance:
    tool: str
    agent_id: str
    inputs_hash: str
    result_hash: str
    golden_version: str | None
    created_utc: str

    def as_dict(self) -> dict:
        return {
            "tool": self.tool,
            "agent_id": self.agent_id,
            "inputs_hash": self.inputs_hash,
            "result_hash": self.result_hash,
            "golden_version": self.golden_version,
            "created_utc": self.created_utc,
        }


def record_provenance(
    tool: str,
    agent_id: str,
    inputs: dict,
    result: dict,
    golden_version: str | None = None,
) -> Provenance:
    """Build a provenance record for one tool call's inputs and result."""
    if not tool:
        raise ValueError("tool must be non-empty")
    if not agent_id:
        raise ValueError("agent_id must be non-empty")
    return Provenance(
        tool=tool,
        agent_id=agent_id,
        inputs_hash=_canonical_hash(inputs),
        result_hash=_canonical_hash(result),
        golden_version=golden_version,
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
