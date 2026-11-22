"""Automated voice-quality evaluation.

Each eval run scores a voice version on four measured dimensions and
combines them into one composite score. A run passes only when every
quality gate holds; a run whose composite score falls below the
quarantine threshold fails the voice outright, so a bad re-train never
reaches customers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Quality gates: every gate must hold for the run to pass.
MIN_INTELLIGIBILITY = 0.70   # fraction of words understood in a listening test
MIN_SIMILARITY = 0.65        # similarity to the reference voice (0-1)
MAX_LATENCY_MS = 800.0       # time to first audio chunk
MIN_COVERAGE = 0.80          # fraction of the multilingual test set covered
QUARANTINE_BELOW = 0.60      # composite score below this quarantines the voice

# Composite weights (sum to 1.0).
WEIGHTS = {
    "intelligibility": 0.35,
    "similarity": 0.35,
    "latency": 0.15,
    "coverage": 0.15,
}


def latency_score(latency_ms: float) -> float:
    """Map latency to 0-1: full marks at or under the gate, 0 at 2x the gate."""
    if latency_ms <= MAX_LATENCY_MS:
        return 1.0
    return max(0.0, 1.0 - (latency_ms - MAX_LATENCY_MS) / MAX_LATENCY_MS)


def composite_score(
    intelligibility: float, similarity: float, latency_ms: float, coverage: float
) -> float:
    """Weighted composite of the four dimensions, rounded to 3 decimals."""
    for name, value in (
        ("intelligibility", intelligibility),
        ("similarity", similarity),
        ("coverage", coverage),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1, got {value}")
    if latency_ms < 0:
        raise ValueError(f"latency_ms must be >= 0, got {latency_ms}")
    score = (
        WEIGHTS["intelligibility"] * intelligibility
        + WEIGHTS["similarity"] * similarity
        + WEIGHTS["latency"] * latency_score(latency_ms)
        + WEIGHTS["coverage"] * coverage
    )
    return round(score, 3)


@dataclass
class EvalResult:
    voice_id: int
    version: str
    intelligibility: float
    similarity: float
    latency_ms: float
    coverage: float
    composite: float
    passed: bool
    quarantine: bool
    failed_gates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "voice_id": self.voice_id,
            "version": self.version,
            "intelligibility": self.intelligibility,
            "similarity": self.similarity,
            "latency_ms": self.latency_ms,
            "coverage": self.coverage,
            "composite": self.composite,
            "passed": self.passed,
            "quarantine": self.quarantine,
            "failed_gates": list(self.failed_gates),
        }


def evaluate(
    voice_id: int,
    version: str,
    intelligibility: float,
    similarity: float,
    latency_ms: float,
    coverage: float,
) -> EvalResult:
    """Score one eval run and apply the quality gates."""
    failed: list[str] = []
    if intelligibility < MIN_INTELLIGIBILITY:
        failed.append(f"intelligibility {intelligibility} < {MIN_INTELLIGIBILITY}")
    if similarity < MIN_SIMILARITY:
        failed.append(f"similarity {similarity} < {MIN_SIMILARITY}")
    if latency_ms > MAX_LATENCY_MS:
        failed.append(f"latency_ms {latency_ms} > {MAX_LATENCY_MS}")
    if coverage < MIN_COVERAGE:
        failed.append(f"coverage {coverage} < {MIN_COVERAGE}")
    composite = composite_score(intelligibility, similarity, latency_ms, coverage)
    quarantine = composite < QUARANTINE_BELOW
    return EvalResult(
        voice_id=voice_id,
        version=version,
        intelligibility=intelligibility,
        similarity=similarity,
        latency_ms=latency_ms,
        coverage=coverage,
        composite=composite,
        passed=not failed and not quarantine,
        quarantine=quarantine,
        failed_gates=failed,
    )
