"""Idea briefs: the raw material of the innovation lab.

An idea is a short, testable brief — a problem, a target user, a
hypothesis about what would help, and a success metric that decides
whether the prototype worked. Nothing ships without a brief: the brief
is what the prototype is validated against, and what the pivot/kill
decision reads back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

REQUIRED_FIELDS = ("title", "problem", "target_user", "hypothesis", "success_metric")


@dataclass
class Idea:
    """A single idea brief."""

    slug: str
    title: str
    problem: str
    target_user: str
    hypothesis: str
    success_metric: str
    status: str = "open"  # open | prototyping | validated | pivoted | killed
    notes: list = field(default_factory=list)


class IdeaStore:
    """In-memory registry of idea briefs."""

    def __init__(self):
        self._ideas = {}

    def create(self, slug, title, problem, target_user, hypothesis, success_metric):
        """Validate and store a new idea brief. Raises ValueError on bad input."""
        if not SLUG_RE.match(slug or ""):
            raise ValueError(f"slug {slug!r} must be lowercase letters, digits and hyphens")
        if slug in self._ideas:
            raise ValueError(f"idea {slug!r} already exists")
        values = {
            "title": title,
            "problem": problem,
            "target_user": target_user,
            "hypothesis": hypothesis,
            "success_metric": success_metric,
        }
        for name in REQUIRED_FIELDS:
            value = values[name]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required and must be non-empty text")
        idea = Idea(slug=slug, **{k: v.strip() for k, v in values.items()})
        self._ideas[slug] = idea
        return idea

    def get(self, slug):
        return self._ideas.get(slug)

    def list(self, status=None):
        ideas = sorted(self._ideas.values(), key=lambda i: i.slug)
        if status is not None:
            ideas = [i for i in ideas if i.status == status]
        return ideas

    def set_status(self, slug, status):
        idea = self.get(slug)
        if idea is None:
            raise ValueError(f"unknown idea {slug!r}")
        allowed = {"open", "prototyping", "validated", "pivoted", "killed"}
        if status not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        idea.status = status
        return idea

    def add_note(self, slug, note):
        idea = self.get(slug)
        if idea is None:
            raise ValueError(f"unknown idea {slug!r}")
        if not isinstance(note, str) or not note.strip():
            raise ValueError("note must be non-empty text")
        idea.notes.append(note.strip())
        return idea
