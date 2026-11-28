"""Demo: fan out 16 agents over 1,200 finance documents, merge, verify, rank.

Prints the question, the merged results, and the measured cost/latency/
precision/recall. Run twice to see the cache make the second run free.
"""
from __future__ import annotations

import time

from swarm.corpus import build_corpus
from swarm.models import REASONER, SCOUT, route
from swarm.orchestrator import SwarmConfig, SwarmOrchestrator


def main() -> None:
    corpus = build_corpus()
    question = corpus.questions[0]
    print(f"Question: {question.text}")
    print(f"Corpus: {len(corpus.documents)} documents, "
          f"{len(corpus.ground_truth(question))} true answers\n")

    config = SwarmConfig(
        n_agents=16,
        map_model=route(question_complexity=0.3, budget_per_doc=0.01),
        verify_model=REASONER,
        verify=True,
    )
    orch = SwarmOrchestrator(corpus, config)

    start = time.perf_counter()
    results, metrics = orch.search(question)
    wall = time.perf_counter() - start
    print(f"Map model (routed): {config.map_model.name}; "
          f"verify model: {config.verify_model.name}")
    print(f"Verified results: {len(results)} "
          f"(top 5: {[c.doc_id for c in results[:5]]})")
    print(f"Precision: {metrics.precision:.3f}  Recall: {metrics.recall:.3f}")
    print(f"Cost: ${metrics.cost_usd:.2f}  "
          f"Cost per useful result: ${metrics.cost_per_useful_result:.4f}")
    print(f"Simulated latency: {metrics.latency_s:.2f}s  "
          f"(wall time: {wall:.2f}s)  Waves: {metrics.waves_run}  "
          f"Agents: {metrics.agents_used}")
    print(f"Docs scanned: {metrics.docs_scanned}")

    # Second run: the cache serves every shard, so nothing is re-scanned.
    results2, metrics2 = orch.search(question)
    print(f"\nSecond run (cached): {len(results2)} results, "
          f"cost ${metrics2.cost_usd:.2f}, docs scanned {metrics2.docs_scanned}, "
          f"cache hits {metrics2.cache_hits} docs")


if __name__ == "__main__":
    main()
