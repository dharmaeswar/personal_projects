"""Tests for entity extraction and knowledge-graph build."""

from kg_rag.corpus import DOCUMENTS
from kg_rag.graph import ENTITIES, KnowledgeGraph, extract_triples, find_entities


def test_find_entities_returns_canonical_forms():
    found = find_entities("Which drug targets BRCA1-mutated breast cancer?")
    assert "BRCA1" in found
    assert "breast cancer" in found


def test_find_entities_longest_match_first():
    found = find_entities("non-small cell lung cancer treatment")
    assert "non-small cell lung cancer" in found


def test_find_entities_empty_for_unknown_text():
    assert find_entities("hello world, nothing biomedical here") == []


def test_extract_triples_targets_relation():
    doc = {"id": "T1", "text": "Olaparib targets BRCA1. BRCA1 is associated with breast cancer."}
    triples = extract_triples(doc)
    assert ("Olaparib", "TARGETS", "BRCA1", "T1") in triples
    assert ("BRCA1", "ASSOCIATED_WITH", "breast cancer", "T1") in triples


def test_extract_triples_skips_non_relation_sentences():
    doc = {"id": "T2", "text": "Patients with BRCA1 mutations show deficiency. Olaparib targets BRCA1."}
    triples = extract_triples(doc)
    assert len(triples) == 1
    assert triples[0][1] == "TARGETS"


def test_extract_triples_skips_self_loops():
    doc = {"id": "T3", "text": "BRCA1 is associated with BRCA1."}
    assert extract_triples(doc) == []


def test_graph_build_counts():
    graph = KnowledgeGraph.build(DOCUMENTS)
    summary = graph.summary()
    assert summary["nodes"] == len(ENTITIES)
    assert summary["edges"] == 46
    assert summary["edges_by_relation"]["TARGETS"] == 8
    assert summary["edges_by_relation"]["TREATS"] == 9
    assert summary["edges_by_relation"]["ASSOCIATED_WITH"] == 14
    assert summary["edges_by_relation"]["INTERACTS_WITH"] == 7
    assert summary["edges_by_relation"]["PART_OF"] == 8


def test_graph_edges_carry_provenance():
    graph = KnowledgeGraph.build(DOCUMENTS)
    for edge in graph.edges:
        assert edge["source"] in {d["id"] for d in DOCUMENTS}
        assert edge["weight"] == 1.0


def test_neighbours_two_hops_reaches_disease():
    graph = KnowledgeGraph.build(DOCUMENTS)
    neighbours, _ = graph.neighbours("Olaparib", hops=2)
    # Olaparib -> BRCA1 -> breast cancer / DNA repair pathway / ovarian cancer
    assert "breast cancer" in neighbours
    assert "DNA repair pathway" in neighbours


def test_neighbours_one_hop_is_direct_only():
    graph = KnowledgeGraph.build(DOCUMENTS)
    neighbours, _ = graph.neighbours("Olaparib", hops=1)
    assert "BRCA1" in neighbours
    # DNA repair pathway is two hops away (Olaparib -> BRCA1 -> pathway).
    assert "DNA repair pathway" not in neighbours


def test_edges_for_returns_typed_edges():
    graph = KnowledgeGraph.build(DOCUMENTS)
    edges = graph.edges_for({"Olaparib"})
    relations = {e["relation"] for e in edges}
    assert "TARGETS" in relations
    assert "TREATS" in relations
