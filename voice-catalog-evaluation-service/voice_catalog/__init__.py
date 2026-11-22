"""Voice catalog + automated voice-quality evaluation service.

Stdlib-only Python. See README.md for the full description.
"""
from voice_catalog.store import Store, Voice, VoiceStatus
from voice_catalog.evaluation import EvalResult, evaluate
from voice_catalog.service import run_eval, analytics_summary

__all__ = [
    "Store",
    "Voice",
    "VoiceStatus",
    "EvalResult",
    "evaluate",
    "run_eval",
    "analytics_summary",
]
