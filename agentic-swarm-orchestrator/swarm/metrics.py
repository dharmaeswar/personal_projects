"""Measurement: cost, latency, yield, and quality of a swarm run.

Everything the orchestrator reports is computed here from the raw counts,
so the numbers in a demo or eval report are never hand-written.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunMetrics:
    docs_scanned: int = 0
    candidates: int = 0
    verified: int = 0
    true_positives: int = 0
    false_positives: int = 0
    ground_truth_size: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0          # simulated wall time (parallel agents)
    cache_hits: int = 0
    waves_run: int = 0
    agents_used: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.ground_truth_size if self.ground_truth_size else 0.0

    @property
    def cost_per_useful_result(self) -> float:
        return self.cost_usd / self.true_positives if self.true_positives else float("inf")

    @property
    def yield_per_dollar(self) -> float:
        return self.true_positives / self.cost_usd if self.cost_usd else 0.0

    def as_dict(self) -> dict:
        return {
            "docs_scanned": self.docs_scanned,
            "candidates": self.candidates,
            "verified": self.verified,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "ground_truth_size": self.ground_truth_size,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "cost_usd": round(self.cost_usd, 4),
            "latency_s": round(self.latency_s, 3),
            "cost_per_useful_result_usd": (
                round(self.cost_per_useful_result, 4)
                if self.true_positives else None
            ),
            "yield_per_dollar": round(self.yield_per_dollar, 2),
            "cache_hits": self.cache_hits,
            "waves_run": self.waves_run,
            "agents_used": self.agents_used,
        }
