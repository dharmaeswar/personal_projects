"""Change Review Signal Analyzer.

A small, self-contained tool that reads a unified diff and produces the
signals a human reviewer needs before approving a change: how big the
change is, which risky patterns it introduces, whether the changed lines
are covered by tests, and who should review it.

All data is synthetic and local. Nothing here talks to a real code-review
system, repository, or CI service, and nothing here claims production use.
"""

from .diffparse import ChangedFile, Hunk, parse_diff
from .signals import ChangeSignals, Finding, analyze_change
from .review import Review, review_change

__all__ = [
    "ChangedFile",
    "Hunk",
    "parse_diff",
    "ChangeSignals",
    "Finding",
    "analyze_change",
    "Review",
    "review_change",
]
