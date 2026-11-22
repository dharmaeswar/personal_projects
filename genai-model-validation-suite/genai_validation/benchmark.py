"""Benchmarking: champion vs challenger vs base-rate benchmark accuracy."""
from __future__ import annotations


def accuracy(model, cases, seed: int = 0) -> dict:
    correct = 0
    confusion = {}
    for case in cases:
        pred = model.generate(case, seed=seed)["decision"]
        truth = case["truth"]
        correct += pred == truth
        confusion.setdefault(truth, {}).setdefault(pred, 0)
        confusion[truth][pred] += 1
    return {"model": model.name, "cases": len(cases),
            "correct": correct,
            "accuracy": round(correct / len(cases), 4) if cases else 0.0,
            "confusion": confusion}


def benchmark(candidate, challenger, benchmark_model, cases, seed: int = 0) -> dict:
    results = {m.name: accuracy(m, cases, seed=seed)
               for m in (candidate, challenger, benchmark_model)}
    champ = results[candidate.name]["accuracy"]
    chal = results[challenger.name]["accuracy"]
    return {"models": results,
            "champion_minus_challenger": round(champ - chal, 4),
            "champion_beats_benchmark": champ > results[benchmark_model.name]["accuracy"]}
