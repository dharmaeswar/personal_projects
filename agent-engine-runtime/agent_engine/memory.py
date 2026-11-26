"""Session memory: short-term working memory + long-term episodic memory.

WorkingMemory is a capped, most-recent-first buffer for the current
session (what the agent is doing right now). EpisodicMemory is a durable
per-tenant store of past turns; recall ranks episodes by token overlap
with the query plus a recency bonus, so the agent remembers relevant
history instead of the whole log. SessionMemory ties the two together:
writes land in both, reads check working memory first, then recall.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass
class Episode:
    text: str
    tenant_id: str
    turn: int
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class RecallHit:
    episode: Episode
    score: float


class WorkingMemory:
    """Short-term buffer: keeps the last `capacity` turns, newest first."""

    def __init__(self, capacity: int = 10):
        self.capacity = capacity
        self._turns: deque = deque(maxlen=capacity)

    def add(self, text: str) -> None:
        self._turns.append(text)

    def recent(self, n: Optional[int] = None) -> List[str]:
        items = list(self._turns)
        return items[-n:] if n else items

    def __len__(self) -> int:
        return len(self._turns)


class EpisodicMemory:
    """Long-term store with token-overlap retrieval and a recency bonus."""

    def __init__(self):
        self._episodes: List[Episode] = []
        self._turn = 0

    def store(self, text: str, tenant_id: str,
              metadata: Optional[Dict[str, str]] = None) -> Episode:
        self._turn += 1
        episode = Episode(text=text, tenant_id=tenant_id, turn=self._turn,
                          metadata=metadata or {})
        self._episodes.append(episode)
        return episode

    def recall(self, query: str, tenant_id: str, top_k: int = 3) -> List[RecallHit]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        now = time.time()
        hits: List[RecallHit] = []
        for episode in self._episodes:
            if episode.tenant_id != tenant_id:
                continue  # tenant isolation: never recall another tenant's past
            overlap = len(query_tokens & _tokens(episode.text))
            if overlap == 0:
                continue
            age_seconds = max(0.0, now - episode.created_at)
            recency = 1.0 / (1.0 + age_seconds / 3600.0)
            score = overlap + 0.25 * recency
            hits.append(RecallHit(episode=episode, score=score))
        hits.sort(key=lambda h: (-h.score, -h.episode.turn))
        return hits[:top_k]

    def __len__(self) -> int:
        return len(self._episodes)


class SessionMemory:
    """One session: working memory for now, episodic memory for history."""

    def __init__(self, tenant_id: str, working_capacity: int = 10):
        self.tenant_id = tenant_id
        self.working = WorkingMemory(capacity=working_capacity)
        self.episodic = EpisodicMemory()

    def remember(self, text: str, metadata: Optional[Dict[str, str]] = None) -> None:
        self.working.add(text)
        self.episodic.store(text, tenant_id=self.tenant_id, metadata=metadata)

    def recall(self, query: str, top_k: int = 3) -> List[RecallHit]:
        return self.episodic.recall(query, tenant_id=self.tenant_id, top_k=top_k)

    def context_block(self, query: str, top_k: int = 3) -> str:
        """Text a step can paste into its prompt: recent turns + recalled past."""
        lines = ["[working memory]"]
        lines.extend(f"- {t}" for t in self.working.recent())
        lines.append("[recalled history]")
        for hit in self.recall(query, top_k=top_k):
            lines.append(f"- ({hit.score:.2f}) {hit.episode.text}")
        return "\n".join(lines)
