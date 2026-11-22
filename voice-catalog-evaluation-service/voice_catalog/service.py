"""Service layer: run evals, keep eval history, summarise analytics.

Running an eval records the result against the voice and, when the
composite score falls below the quarantine threshold, moves the voice
to quarantined status automatically — a bad version is pulled from the
catalog instead of shipping to customers.
"""
from __future__ import annotations

from collections import defaultdict

from voice_catalog.evaluation import EvalResult, evaluate
from voice_catalog.store import Store, VoiceStatus


class EvalHistory:
    """Eval runs per voice, newest last."""

    def __init__(self) -> None:
        self._runs: dict[int, list[EvalResult]] = defaultdict(list)

    def add(self, result: EvalResult) -> None:
        self._runs[result.voice_id].append(result)

    def for_voice(self, voice_id: int) -> list[EvalResult]:
        return list(self._runs.get(voice_id, []))

    def all_runs(self) -> list[EvalResult]:
        return [r for runs in self._runs.values() for r in runs]


def run_eval(
    store: Store,
    history: EvalHistory,
    voice_id: int,
    version: str,
    intelligibility: float,
    similarity: float,
    latency_ms: float,
    coverage: float,
) -> EvalResult:
    """Evaluate a voice version; quarantine the voice on a failing score."""
    voice = store.get_voice(voice_id)
    if version and not any(v.version == version for v in voice.versions):
        raise ValueError(f"voice {voice_id} has no version {version!r}")
    result = evaluate(voice_id, version, intelligibility, similarity, latency_ms, coverage)
    history.add(result)
    if result.quarantine:
        store.set_status(voice_id, VoiceStatus.QUARANTINED)
    return result


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def analytics_summary(store: Store, history: EvalHistory) -> dict:
    """Catalog analytics: mean scores, pass rate, per-language coverage."""
    runs = history.all_runs()
    voices = store.list_voices()
    per_language: dict[str, dict] = {}
    for voice in voices:
        bucket = per_language.setdefault(
            voice.language, {"voices": 0, "active": 0, "quarantined": 0, "evals": 0}
        )
        bucket["voices"] += 1
        if voice.status == VoiceStatus.ACTIVE:
            bucket["active"] += 1
        if voice.status == VoiceStatus.QUARANTINED:
            bucket["quarantined"] += 1
        bucket["evals"] += len(history.for_voice(voice.id))
    return {
        "voices": len(voices),
        "active": sum(1 for v in voices if v.status == VoiceStatus.ACTIVE),
        "draft": sum(1 for v in voices if v.status == VoiceStatus.DRAFT),
        "quarantined": sum(1 for v in voices if v.status == VoiceStatus.QUARANTINED),
        "eval_runs": len(runs),
        "pass_rate": round(sum(1 for r in runs if r.passed) / len(runs), 3) if runs else 0.0,
        "mean_composite": _mean([r.composite for r in runs]),
        "mean_intelligibility": _mean([r.intelligibility for r in runs]),
        "mean_similarity": _mean([r.similarity for r in runs]),
        "mean_latency_ms": _mean([r.latency_ms for r in runs]),
        "per_language": per_language,
    }
