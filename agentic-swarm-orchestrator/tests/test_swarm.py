"""Tests for the agentic swarm orchestrator."""
from __future__ import annotations

import pytest

from swarm.corpus import Corpus, Document, Question, build_corpus
from swarm.metrics import RunMetrics
from swarm.models import REASONER, SCOUT, STANDARD, route, scan_document
from swarm.orchestrator import (
    SwarmConfig,
    SwarmOrchestrator,
    shard_documents,
)
from swarm.verify import precision_recall, sample_precision, verify_candidate, vote


@pytest.fixture(scope="module")
def corpus():
    return build_corpus()


@pytest.fixture(scope="module")
def question(corpus):
    return corpus.questions[0]


# --- corpus ---

def test_corpus_size_and_ground_truth(corpus):
    assert len(corpus.documents) == 1200
    assert len(corpus.questions) == 6
    truth = corpus.ground_truth(corpus.questions[0])
    assert len(truth) == 120  # one topic in ten
    assert all(d.startswith("DOC-") for d in truth)


def test_corpus_is_deterministic():
    a = build_corpus()
    b = build_corpus()
    assert [d.text for d in a.documents] == [d.text for d in b.documents]


# --- sharding ---

def test_shards_cover_every_doc_exactly_once(corpus):
    shards = shard_documents(corpus.documents, 16)
    assert len(shards) == 16
    flat = [d.doc_id for shard in shards for d in shard]
    assert len(flat) == len(set(flat)) == 1200


def test_shards_reject_zero():
    with pytest.raises(ValueError):
        shard_documents([], 0)


def test_empty_corpus_shards_to_nothing():
    assert shard_documents([], 4) == []


# --- simulated models ---

def test_scan_is_deterministic():
    a = scan_document(SCOUT, "DOC-0001", "Q1", True)
    b = scan_document(SCOUT, "DOC-0001", "Q1", True)
    assert a == b


def test_reasoner_recalls_more_than_scout(corpus, question):
    truth = corpus.ground_truth(question)
    for model in (SCOUT, STANDARD, REASONER):
        hits = sum(
            1 for d in corpus.documents
            if scan_document(model, d.doc_id, question.question_id,
                             d.doc_id in truth) is not None
            and d.doc_id in truth
        )
        assert hits > 0
    scout_hits = sum(
        1 for d in corpus.documents
        if scan_document(SCOUT, d.doc_id, question.question_id,
                         d.doc_id in truth) is not None and d.doc_id in truth)
    reasoner_hits = sum(
        1 for d in corpus.documents
        if scan_document(REASONER, d.doc_id, question.question_id,
                         d.doc_id in truth) is not None and d.doc_id in truth)
    assert reasoner_hits >= scout_hits


def test_router_picks_cheapest_that_fits():
    assert route(0.2, 0.01).name == "scout-small"
    assert route(0.5, 0.05).name == "standard"
    assert route(0.9, 0.10).name == "reasoner-large"
    # A hard question with a tight budget falls back to the scout.
    assert route(0.9, 0.005).name == "scout-small"


# --- verification ---

def test_vote_needs_min_votes():
    assert vote([{"a", "b"}, {"b", "c"}, {"b"}], min_votes=2) == {"b"}
    assert vote([{"a"}, {"b"}], min_votes=2) == set()


def test_precision_recall_math():
    p, r = precision_recall({"a", "b", "c"}, {"b", "c", "d", "e"})
    assert p == pytest.approx(2 / 3)
    assert r == pytest.approx(2 / 4)
    assert precision_recall(set(), {"a"}) == (0.0, 0.0)


def test_sample_precision_matches_full_when_sample_is_all():
    found = [f"DOC-{i:04d}" for i in range(1, 11)]
    truth = set(found[:6])
    est, n = sample_precision(found, truth, 10)
    assert n == 10
    assert est == pytest.approx(0.6)


def test_verify_keeps_most_true_positives_and_drops_most_false_positives(corpus, question):
    truth = corpus.ground_truth(question)
    tp_kept = sum(1 for d in list(truth)[:40]
                  if verify_candidate(REASONER, d, question.question_id, True))
    fp_kept = sum(1 for d in [f"DOC-{i:04d}" for i in range(2, 82, 10)
                              if f"DOC-{i:04d}" not in truth]
                  if verify_candidate(REASONER, d, question.question_id, False))
    assert tp_kept >= 36  # verify_recall 0.97
    assert fp_kept <= 2   # verify_fp_reject 0.90


# --- orchestrator ---

def test_search_returns_ranked_verified_results(corpus, question):
    orch = SwarmOrchestrator(corpus, SwarmConfig(n_agents=16, map_model=SCOUT))
    results, metrics = orch.search(question)
    assert len(results) > 0
    scores = [c.score for c in results]
    assert scores == sorted(scores, reverse=True)
    assert metrics.true_positives > 0
    assert metrics.precision > 0.5  # verification keeps precision up
    assert metrics.docs_scanned == 1200
    assert metrics.ground_truth_size == 120


def test_fanout_beats_single_agent_recall(corpus, question):
    single = SwarmOrchestrator(corpus, SwarmConfig(n_agents=1, map_model=SCOUT,
                                                   verify=False, early_stop=False))
    _, m1 = single.search(question)
    fan = SwarmOrchestrator(corpus, SwarmConfig(n_agents=16, map_model=SCOUT,
                                                verify=False, early_stop=False))
    _, m2 = fan.search(question)
    assert m2.recall >= m1.recall  # same model, same docs: identical scan set
    assert m2.latency_s < m1.latency_s  # parallel shards finish sooner


def test_no_verification_means_lower_precision(corpus, question):
    orch = SwarmOrchestrator(corpus, SwarmConfig(n_agents=16, map_model=SCOUT,
                                                 verify=False, early_stop=False))
    _, metrics = orch.search(question)
    assert metrics.false_positives > 0
    assert metrics.precision < 1.0


def test_cache_makes_repeat_search_free(corpus, question):
    orch = SwarmOrchestrator(corpus, SwarmConfig(n_agents=16, map_model=SCOUT))
    _, m1 = orch.search(question)
    _, m2 = orch.search(question)
    assert m2.docs_scanned == 0
    assert m2.cost_usd == pytest.approx(0.0)
    assert m2.cache_hits == 1200
    assert m1.true_positives == m2.true_positives


def test_early_stop_when_later_waves_add_nothing():
    # Corpus where only the first shard holds answers: later waves add zero.
    docs = [Document(doc_id=f"DOC-{i:04d}", topic="invoice" if i < 10 else "tax",
                     text="x") for i in range(120)]
    q = Question("Q1", "invoice?", "invoice", ("invoice",))
    corpus = Corpus(documents=docs, questions=[q])
    orch = SwarmOrchestrator(
        corpus,
        SwarmConfig(n_agents=12, map_model=STANDARD, wave_size=4,
                    min_waves=2, early_stop=True))
    _, metrics = orch.search(q)
    assert metrics.waves_run == 2  # stopped after the first empty wave
    assert metrics.docs_scanned == 80  # 2 waves x 4 shards x 10 docs


def test_budget_cap_stops_the_run(corpus, question):
    orch = SwarmOrchestrator(
        corpus, SwarmConfig(n_agents=16, map_model=REASONER, budget_usd=0.10,
                            early_stop=False))
    _, metrics = orch.search(question)
    assert metrics.cost_usd <= 0.10 + 16 * 75 * 0.05  # at most one wave over
    assert metrics.waves_run <= 1


def test_empty_corpus_returns_nothing():
    orch = SwarmOrchestrator(Corpus(documents=[], questions=[]))
    q = Question("Q1", "?", "invoice", ("invoice",))
    results, metrics = orch.search(q)
    assert results == []
    assert metrics.docs_scanned == 0


def test_metrics_cost_per_useful_result():
    m = RunMetrics(true_positives=10, cost_usd=2.0)
    assert m.cost_per_useful_result == pytest.approx(0.2)
    assert RunMetrics().cost_per_useful_result == float("inf")


def test_more_agents_stop_helping_is_measurable(corpus, question):
    """Marginal yield: doubling agents past full coverage adds no recall."""
    orch = SwarmOrchestrator(corpus, SwarmConfig(n_agents=16, map_model=STANDARD,
                                                 verify=True, early_stop=False))
    _, m16 = orch.search(question)
    orch32 = SwarmOrchestrator(corpus, SwarmConfig(n_agents=32, map_model=STANDARD,
                                                   verify=True, early_stop=False))
    _, m32 = orch32.search(question)
    assert m32.recall == pytest.approx(m16.recall)
    assert m32.cost_usd >= m16.cost_usd
