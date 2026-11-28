"""Fan-out orchestrator: agentic map-reduce over a large search space.

Map: the corpus is split into shards and one agent scans each shard in
parallel (ThreadPoolExecutor), returning partial results. Reduce: results
are deduplicated, verified by an independent pass, and ranked. The run
stops early when another wave of agents adds no new verified results, and
shard results are cached so a repeat search costs nothing.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .corpus import Corpus, Question
from .metrics import RunMetrics
from .models import Candidate, ModelProfile, REASONER, SCOUT, scan_document
from .verify import verify_candidate


@dataclass
class SwarmConfig:
    n_agents: int = 16
    map_model: ModelProfile = SCOUT
    verify_model: ModelProfile = REASONER
    verify: bool = True
    wave_size: int = 4       # shards launched per wave
    min_waves: int = 2       # always run at least this many waves
    early_stop: bool = True  # stop when a wave adds no new verified results
    budget_usd: float = 50.0
    use_cache: bool = True


def shard_documents(documents: list, n_shards: int) -> list[list]:
    """Split documents into ``n_shards`` contiguous, disjoint shards that
    together cover every document exactly once."""
    if n_shards <= 0:
        raise ValueError("n_shards must be positive")
    if not documents:
        return []
    size = (len(documents) + n_shards - 1) // n_shards
    return [documents[i:i + size] for i in range(0, len(documents), size)]


@dataclass
class SwarmOrchestrator:
    corpus: Corpus
    config: SwarmConfig = field(default_factory=SwarmConfig)
    cache: dict = field(default_factory=dict)  # (question, shard, model) -> candidates
    _verify_cache: dict = field(default_factory=dict)  # (model, doc, question) -> bool

    def _scan_shard(self, shard: list, shard_idx: int, question: Question,
                    truth: set[str]):
        """One agent scans one shard.

        Returns (candidates, docs_scanned, cost, latency, served_from_cache,
        docs_in_shard). Cached shards cost nothing and scan nothing on this run.
        """
        key = (question.question_id, shard_idx, self.config.map_model.name)
        if self.config.use_cache and key in self.cache:
            return self.cache[key], 0, 0.0, 0.0, True, len(shard)
        model = self.config.map_model
        found: list[Candidate] = []
        for doc in shard:
            cand = scan_document(model, doc.doc_id, question.question_id,
                                 doc.doc_id in truth)
            if cand is not None:
                found.append(cand)
        cost = len(shard) * model.cost_per_doc
        latency = len(shard) * model.latency_per_doc
        if self.config.use_cache:
            self.cache[key] = found
        return found, len(shard), cost, latency, False, len(shard)

    def search(self, question: Question) -> tuple[list[Candidate], RunMetrics]:
        truth = self.corpus.ground_truth(question)
        metrics = RunMetrics(ground_truth_size=len(truth))
        shards = shard_documents(self.corpus.documents, self.config.n_agents)
        if not shards:
            return [], metrics

        verified: dict[str, Candidate] = {}  # doc_id -> best candidate
        waves = [shards[i:i + self.config.wave_size]
                 for i in range(0, len(shards), self.config.wave_size)]

        for wave_idx, wave in enumerate(waves):
            if metrics.cost_usd >= self.config.budget_usd:
                break
            with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                futures = [
                    pool.submit(self._scan_shard, shard,
                                wave_idx * self.config.wave_size + j,
                                question, truth)
                    for j, shard in enumerate(wave)
                ]
                wave_results = [f.result() for f in futures]
            metrics.waves_run += 1
            metrics.agents_used += len(wave)
            wave_latency = 0.0
            new_candidates: list[Candidate] = []
            for found, n_scanned, cost, latency, cached, n_docs in wave_results:
                metrics.cost_usd += cost
                wave_latency = max(wave_latency, latency)
                if cached:
                    metrics.cache_hits += n_docs
                else:
                    metrics.docs_scanned += n_scanned
                new_candidates.extend(found)
            # Dedup: keep the highest score per doc.
            merged: dict[str, Candidate] = {}
            for cand in new_candidates:
                prev = merged.get(cand.doc_id)
                if prev is None or cand.score > prev.score:
                    merged[cand.doc_id] = cand
            metrics.candidates += len(merged)
            # Verification pass on candidates not already verified.
            fresh = [c for c in merged.values() if c.doc_id not in verified]
            kept: list[Candidate] = []
            if self.config.verify:
                for cand in fresh:
                    vkey = (self.config.verify_model.name, cand.doc_id,
                            question.question_id)
                    if vkey in self._verify_cache:
                        ok = self._verify_cache[vkey]
                    else:
                        metrics.cost_usd += self.config.verify_model.cost_per_doc
                        ok = verify_candidate(
                            self.config.verify_model, cand.doc_id,
                            question.question_id, cand.doc_id in truth)
                        self._verify_cache[vkey] = ok
                    if ok:
                        kept.append(cand)
            else:
                kept = fresh
            metrics.verified += len(kept)
            new_verified = 0
            for cand in kept:
                if cand.doc_id not in verified:
                    verified[cand.doc_id] = cand
                    new_verified += 1
            metrics.latency_s += wave_latency + 0.05  # merge overhead per wave
            if (self.config.early_stop and metrics.waves_run >= self.config.min_waves
                    and new_verified == 0):
                break

        for cand in verified.values():
            if cand.doc_id in truth:
                metrics.true_positives += 1
            else:
                metrics.false_positives += 1
        return sorted(verified.values(), key=lambda c: -c.score), metrics
