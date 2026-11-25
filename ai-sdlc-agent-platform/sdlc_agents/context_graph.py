"""Graph-based context grounding for LLM agents.

An agent that answers from the wrong file wastes turns. This module keeps a
small knowledge graph over a codebase — files, functions, tests and tickets —
and resolves a task to the nodes it actually needs, so the agent gets the
right context on the first try instead of searching turn after turn.

Entity resolution: a query term can name a function, a file, or a ticket id.
A match on a function also pulls in its file, its tests and the tickets that
mention it (one-hop boost), because that is usually what the agent needs
next. Nothing here calls a model; the graph is the context system an LLM
application would feed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "when",
    "then", "need", "should", "please", "task", "code", "file",
}


def tokenize(text: str) -> set[str]:
    """Lowercase word tokens, minus stopwords; underscores split too."""
    words: set[str] = set()
    for raw in TOKEN_RE.findall(text.lower()):
        for part in raw.split("_"):
            if len(part) >= 3 and part not in STOPWORDS:
                words.add(part)
    return words


@dataclass
class Node:
    node_id: str
    kind: str  # file | function | test | ticket
    name: str
    text: str = ""
    tokens: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = tokenize(f"{self.name} {self.text}")


@dataclass
class Edge:
    src: str
    dst: str
    relation: str  # defines | imports | calls | tested_by | fixes | mentions


class ContextGraph:
    """Directed entity graph with ranked first-try grounding."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.outgoing: dict[str, list[Edge]] = {}
        self.incoming: dict[str, list[Edge]] = {}

    def add_node(self, node: Node) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, src: str, dst: str, relation: str) -> None:
        if src not in self.nodes or dst not in self.nodes:
            raise ValueError(f"edge references unknown node: {src} -> {dst}")
        edge = Edge(src, dst, relation)
        self.outgoing.setdefault(src, []).append(edge)
        self.incoming.setdefault(dst, []).append(edge)

    def neighbours(self, node_id: str) -> list[str]:
        seen: list[str] = []
        for edge in self.outgoing.get(node_id, []) + self.incoming.get(node_id, []):
            other = edge.dst if edge.src == node_id else edge.src
            if other not in seen:
                seen.append(other)
        return seen

    def ground(self, query: str, top_k: int = 3) -> list[tuple[Node, float]]:
        """Rank nodes for a query. Direct token overlap scores 1.0 per term;
        one-hop neighbours of a matching node get a 0.5 boost per shared term,
        so a matched function pulls in its file, tests and tickets."""
        terms = tokenize(query)
        if not terms:
            return []
        scores: dict[str, float] = {}
        for node in self.nodes.values():
            overlap = len(terms & node.tokens)
            if overlap:
                scores[node.node_id] = overlap
                for nb in self.neighbours(node.node_id):
                    scores[nb] = scores.get(nb, 0.0) + 0.5 * overlap
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(self.nodes[nid], score) for nid, score in ranked[:top_k]]

    def first_try_hit_rate(self, queries: list[tuple[str, str]], top_k: int = 3) -> float:
        """Fraction of (query, expected node id) pairs where the expected node
        is in the top-k on the first retrieval — no follow-up turns."""
        if not queries:
            return 0.0
        hits = 0
        for query, expected in queries:
            top = [node.node_id for node, _ in self.ground(query, top_k=top_k)]
            if expected in top:
                hits += 1
        return hits / len(queries)
