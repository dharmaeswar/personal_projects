"""Deterministic text-to-SQL stand-in for the analytics agent.

A production analytics agent would call a text-to-SQL model through a
model gateway. This module is the deterministic stand-in used so the
eval harness is reproducible with no model API calls: it translates the
small set of question patterns the eval task set uses, and raises a
clear error for anything outside them instead of guessing SQL.

Honest limit: this is pattern matching, not a model. The eval harness
measures the agent workflow around it (planning, tool calls, validation,
failure handling, provenance) — not text-to-SQL quality itself.
"""

from __future__ import annotations

import re

COMMUNITIES = {"python", "datascience", "machinelearning",
               "learnprogramming", "statistics"}


class TranslationError(Exception):
    """The question is outside the translator's supported patterns."""


def _community(question: str) -> str:
    lowered = question.lower()
    for name in COMMUNITIES:
        if name in lowered:
            return name
    raise TranslationError(
        f"no known community in question: {question!r} "
        f"(known: {sorted(COMMUNITIES)})"
    )


def _days(question: str, default: int = 7) -> int:
    match = re.search(r"last (\d+) days?", question.lower())
    return int(match.group(1)) if match else default


def _since(days: int) -> int:
    # created_day 0..29, day 29 is today; last N days means day >= 30 - N.
    return 30 - days


def translate(question: str) -> str:
    """Translate a supported analytics question to SQL."""
    q = question.lower().strip()

    top = re.search(r"which (\d+) communities have the most posts", q)
    if top:
        n = int(top.group(1))
        since = _since(_days(q))
        return (
            "SELECT community, COUNT(*) AS post_count FROM posts "
            f"WHERE created_day >= {since} GROUP BY community "
            f"ORDER BY post_count DESC, community ASC LIMIT {n}"
        )

    if "highest average score" in q and "at least" in q:
        minimum = int(re.search(r"at least (\d+) posts", q).group(1))
        return (
            "SELECT community, AVG(score) AS avg_score FROM posts "
            "GROUP BY community HAVING COUNT(*) >= "
            f"{minimum} ORDER BY avg_score DESC LIMIT 1"
        )

    if "average score" in q:
        community = _community(q)
        return (
            "SELECT AVG(score) AS avg_score FROM posts "
            f"WHERE community = '{community}'"
        )

    if "how many posts per day" in q:
        community = _community(q)
        since = _since(_days(q, 3))
        return (
            "SELECT created_day, COUNT(*) AS post_count FROM posts "
            f"WHERE community = '{community}' AND created_day >= {since} "
            "GROUP BY created_day ORDER BY created_day ASC"
        )

    if "how many posts" in q:
        community = _community(q)
        since = _since(_days(q, 14))
        return (
            "SELECT COUNT(*) AS post_count FROM posts "
            f"WHERE community = '{community}' AND created_day >= {since}"
        )

    if "total comments" in q:
        community = _community(q)
        since = _since(_days(q))
        return (
            "SELECT SUM(comments) AS total_comments FROM posts "
            f"WHERE community = '{community}' AND created_day >= {since}"
        )

    if "total score" in q:
        community = _community(q)
        return (
            "SELECT SUM(score) AS total_score FROM posts "
            f"WHERE community = '{community}'"
        )

    highest = re.search(r"(\d+) highest-scored posts", q)
    if highest:
        community = _community(q)
        return (
            "SELECT id, title, score FROM posts "
            f"WHERE community = '{community}' "
            f"ORDER BY score DESC LIMIT {int(highest.group(1))}"
        )

    raise TranslationError(
        f"question pattern not supported: {question!r}. "
        "The agent reports this as an incomplete task instead of guessing."
    )
