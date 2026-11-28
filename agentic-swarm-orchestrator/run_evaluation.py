"""Evaluation: compare three swarm configs across the six seeded questions.

- single: one agent, standard model, no verification (the "one agent, one
  trace, a person reads the result" baseline).
- fanout: 16 parallel agents, standard model, no verification.
- swarm: 16 agents, scout for the map phase, reasoner for verification,
  caching + early stopping (the full orchestrator).

Writes swarm_eval_report.json and prints a comparison table.
"""
from __future__ import annotations

import json

from swarm.corpus import build_corpus
from swarm.models import REASONER, SCOUT, STANDARD
from swarm.orchestrator import SwarmConfig, SwarmOrchestrator
from swarm.verify import precision_recall, sample_precision


def run_config(corpus, name, config) -> dict:
    orch = SwarmOrchestrator(corpus, config)
    totals = {"precision": 0.0, "recall": 0.0, "cost": 0.0,
              "latency": 0.0, "cost_per_useful": 0.0, "questions": 0}
    per_question = []
    for question in corpus.questions:
        results, metrics = orch.search(question)
        truth = corpus.ground_truth(question)
        precision, recall = precision_recall({c.doc_id for c in results}, truth)
        sampled, n = sample_precision([c.doc_id for c in results], truth, 20)
        totals["precision"] += precision
        totals["recall"] += recall
        totals["cost"] += metrics.cost_usd
        totals["latency"] += metrics.latency_s
        totals["cost_per_useful"] += metrics.cost_per_useful_result or 0.0
        totals["questions"] += 1
        per_question.append({
            "question": question.question_id,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "sampled_precision_20": round(sampled, 3),
            "sample_checked": n,
            "cost_usd": round(metrics.cost_usd, 2),
            "latency_s": round(metrics.latency_s, 2),
            "true_positives": metrics.true_positives,
        })
    n = totals["questions"]
    return {
        "config": name,
        "mean_precision": round(totals["precision"] / n, 3),
        "mean_recall": round(totals["recall"] / n, 3),
        "total_cost_usd": round(totals["cost"], 2),
        "total_latency_s": round(totals["latency"], 2),
        "mean_cost_per_useful_result_usd": round(totals["cost_per_useful"] / n, 4),
        "per_question": per_question,
    }


def main() -> None:
    corpus = build_corpus()
    configs = [
        ("single-agent-standard-no-verify",
         SwarmConfig(n_agents=1, map_model=STANDARD, verify=False,
                     early_stop=False)),
        ("fanout-16-standard-no-verify",
         SwarmConfig(n_agents=16, map_model=STANDARD, verify=False,
                     early_stop=False)),
        ("swarm-16-scout-map-reasoner-verify-cache-early-stop",
         SwarmConfig(n_agents=16, map_model=SCOUT, verify_model=REASONER,
                     verify=True, use_cache=True, early_stop=True)),
    ]
    report = {"corpus_docs": len(corpus.documents),
              "questions": len(corpus.questions), "configs": []}
    for name, config in configs:
        result = run_config(corpus, name, config)
        report["configs"].append(result)
        print(f"{name}: precision {result['mean_precision']:.3f}, "
              f"recall {result['mean_recall']:.3f}, "
              f"cost ${result['total_cost_usd']:.2f}, "
              f"latency {result['total_latency_s']:.1f}s, "
              f"cost/useful ${result['mean_cost_per_useful_result_usd']:.4f}")
    with open("swarm_eval_report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    print("\nWrote swarm_eval_report.json")


if __name__ == "__main__":
    main()
