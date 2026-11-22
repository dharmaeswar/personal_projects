"""Orchestrate the full independent validation run."""
from __future__ import annotations

from .benchmark import benchmark
from .candidate import BenchmarkModel, CandidateModel, ChallengerModel
from .checks import explainability, psi, reliability, sensitivity
from .data import CASES
from .groundedness import groundedness, hallucination_rate
from .report import build_report


def run_validation(cases=None, seeds=(0, 1, 2, 3, 4)) -> dict:
    cases = list(cases or CASES)
    candidate = CandidateModel()
    challenger = ChallengerModel()
    bench_model = BenchmarkModel(cases)

    # 1. Conceptual soundness proxy: every cited number must be grounded.
    base_runs = [candidate.generate(c, seed=0) for c in cases]
    ground = [groundedness(r["explanation"], c["facts"])
              for r, c in zip(base_runs, cases)]
    hall = hallucination_rate(ground)

    # 2. Outcomes analysis: champion vs challenger vs benchmark.
    bench = benchmark(candidate, challenger, bench_model, cases, seed=0)

    # 3. Output reliability across repeat runs (seeds 0-4 include fault seeds).
    rel = reliability(candidate, cases, seeds=seeds)

    # 4. Sensitivity / stress: prompt rewording must not flip decisions.
    sens = sensitivity(candidate, cases)

    # 5. Stability / drift: utilization-score distribution vs reference.
    ref_scores = [c["facts"]["utilization"] / 100 for c in cases]
    drifted = [min(1.0, s + 0.25) for s in ref_scores]  # stressed input mix
    drift = {"psi": psi(ref_scores, drifted),
             "note": "reference vs +25pp utilization stress mix"}

    # 6. Explainability: do explanations cite the decision-driving facts?
    drivers = ["utilization", "months_delinquent"]
    covs = [explainability(r["explanation"], c["facts"], drivers)["coverage"]
            for r, c in zip(base_runs, cases)]
    expl = {"mean_coverage": round(sum(covs) / len(covs), 4) if covs else 0.0,
            "drivers": drivers}

    results = {
        "cases": len(cases),
        "hallucination": hall,
        "groundedness_per_case": ground,
        "benchmark": bench,
        "reliability": rel,
        "sensitivity": sens,
        "drift": drift,
        "explainability": expl,
    }
    results["report"] = build_report(results)
    return results
