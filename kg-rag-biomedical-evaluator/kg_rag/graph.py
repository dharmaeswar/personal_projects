"""Deterministic entity/relation extraction and knowledge-graph build.

The extractor is rule-based over a seeded entity lexicon and a small set of
relation sentence patterns. It is a stand-in for a real extraction model
(for example a fine-tuned transformer or an LLM extractor); the graph it
produces has the same shape a model-backed extractor would produce, with
provenance (source document) on every edge.
"""

import re
from collections import defaultdict

# Entity lexicon: canonical surface form -> node type.
ENTITIES = {
    # Genes
    "BRCA1": "Gene",
    "TP53": "Gene",
    "EGFR": "Gene",
    "APOE": "Gene",
    "KRAS": "Gene",
    "BRAF": "Gene",
    "PIK3CA": "Gene",
    # Proteins
    "HER2": "Protein",
    "PD-L1": "Protein",
    "amyloid-beta": "Protein",
    "Tau": "Protein",
    # Diseases
    "breast cancer": "Disease",
    "non-small cell lung cancer": "Disease",
    "melanoma": "Disease",
    "colorectal cancer": "Disease",
    "Alzheimer's disease": "Disease",
    "ovarian cancer": "Disease",
    # Drugs
    "Olaparib": "Drug",
    "Osimertinib": "Drug",
    "Trastuzumab": "Drug",
    "Pembrolizumab": "Drug",
    "Dabrafenib": "Drug",
    "Donanemab": "Drug",
    # Pathways
    "DNA repair pathway": "Pathway",
    "MAPK signaling pathway": "Pathway",
    "PI3K-AKT signaling pathway": "Pathway",
    "immune checkpoint pathway": "Pathway",
}

# (regex, relation) — matched against one sentence at a time. Groups 1 and 2
# are the two entity surface forms, in subject -> object order.
RELATION_PATTERNS = [
    (re.compile(r"(.+?)\s+targets\s+(.+?)\.?$"), "TARGETS"),
    (re.compile(r"(.+?)\s+treats\s+(.+?)\.?$"), "TREATS"),
    (re.compile(r"(.+?)\s+is associated with\s+(.+?)\.?$"), "ASSOCIATED_WITH"),
    (re.compile(r"(.+?)\s+interacts with\s+(.+?)\.?$"), "INTERACTS_WITH"),
    (re.compile(r"(.+?)\s+is part of the\s+(.+?)\.?$"), "PART_OF"),
]

# Longest-first matching so "non-small cell lung cancer" wins over "lung
# cancer" and "MAPK signaling pathway" wins over "MAPK".
_SORTED_ENTITIES = sorted(ENTITIES, key=len, reverse=True)


def find_entities(text):
    """Return the entities mentioned in `text`, longest match first.

    Matching is case-insensitive for the lookup but returns the canonical
    lexicon form. Each entity is returned at most once, in order of first
    appearance.
    """
    found = []
    lowered = text.lower()
    for ent in _SORTED_ENTITIES:
        idx = lowered.find(ent.lower())
        if idx >= 0:
            found.append((idx, ent))
    found.sort()
    return [ent for _, ent in found]


def _resolve_entity(fragment):
    """Resolve a sentence fragment to a lexicon entity, or None.

    The fragment is the text on one side of the relation verb; it may carry
    extra words ("Patients with BRCA1 mutations" does not match a pattern,
    so it never reaches here). Matching is exact on the trimmed fragment,
    falling back to the longest entity contained in it.
    """
    frag = fragment.strip().rstrip(".")
    for ent in _SORTED_ENTITIES:
        if frag.lower() == ent.lower():
            return ent
    for ent in _SORTED_ENTITIES:
        if ent.lower() in frag.lower():
            return ent
    return None


def extract_triples(document):
    """Extract (subject, relation, object, doc_id) triples from one document."""
    triples = []
    for sentence in document["text"].split(". "):
        sentence = sentence.strip().rstrip(".")
        if not sentence:
            continue
        for pattern, relation in RELATION_PATTERNS:
            m = pattern.match(sentence)
            if not m:
                continue
            subj = _resolve_entity(m.group(1))
            obj = _resolve_entity(m.group(2))
            if subj and obj and subj != obj:
                triples.append((subj, relation, obj, document["id"]))
            break
    return triples


class KnowledgeGraph:
    """Typed directed multigraph with provenance and edge weights."""

    def __init__(self):
        self.node_types = {}  # entity -> type
        self.edges = []  # dicts: subj, relation, obj, source, weight
        self._adj = defaultdict(list)  # entity -> edge indexes

    def add_document(self, document):
        for subj, relation, obj, doc_id in extract_triples(document):
            self.node_types.setdefault(subj, ENTITIES[subj])
            self.node_types.setdefault(obj, ENTITIES[obj])
            edge = {"subj": subj, "relation": relation, "obj": obj,
                    "source": doc_id, "weight": 1.0}
            self._adj[subj].append(len(self.edges))
            self._adj[obj].append(len(self.edges))
            self.edges.append(edge)

    def add_edge(self, subj, subj_type, relation, obj, obj_type, source,
                 weight=1.0):
        """Add one typed edge with provenance (used by the bioassay ETL)."""
        self.node_types.setdefault(subj, subj_type)
        self.node_types.setdefault(obj, obj_type)
        edge = {"subj": subj, "relation": relation, "obj": obj,
                "source": source, "weight": weight}
        self._adj[subj].append(len(self.edges))
        self._adj[obj].append(len(self.edges))
        self.edges.append(edge)

    @classmethod
    def build(cls, documents):
        graph = cls()
        for doc in documents:
            graph.add_document(doc)
        return graph

    def neighbours(self, entity, hops=1):
        """All entities within `hops` edges of `entity`, with the edges used."""
        seen = {entity}
        frontier = {entity}
        found_edges = []
        for _ in range(hops):
            nxt = set()
            for node in frontier:
                for idx in self._adj.get(node, []):
                    edge = self.edges[idx]
                    found_edges.append(edge)
                    other = edge["obj"] if edge["subj"] == node else edge["subj"]
                    if other not in seen:
                        seen.add(other)
                        nxt.add(other)
            frontier = nxt
        seen.discard(entity)
        return seen, found_edges

    def edges_for(self, entities):
        """Edges touching any of `entities`, de-duplicated, weight order."""
        out = {}
        for ent in entities:
            for idx in self._adj.get(ent, []):
                edge = self.edges[idx]
                key = (edge["subj"], edge["relation"], edge["obj"])
                out[key] = edge
        return sorted(out.values(), key=lambda e: -e["weight"])

    def summary(self):
        by_type = defaultdict(int)
        for node, ntype in self.node_types.items():
            by_type[ntype] += 1
        by_relation = defaultdict(int)
        for edge in self.edges:
            by_relation[edge["relation"]] += 1
        return {
            "nodes": len(self.node_types),
            "edges": len(self.edges),
            "nodes_by_type": dict(sorted(by_type.items())),
            "edges_by_relation": dict(sorted(by_relation.items())),
        }
