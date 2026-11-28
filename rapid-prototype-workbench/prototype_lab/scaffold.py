"""Prototype scaffolding: idea brief -> working prototype, in minutes.

A prototype is the smallest working slice of an idea across the whole
stack: a JSON API, a data pipeline that records usage, and a frontend
page a real user can open. The scaffold is generated from the brief so
every prototype carries the same shape — API routes, pipeline stages,
and a page — and can be built, run, and measured the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The fixed stack shape every prototype gets: API, pipeline, page.
DEFAULT_API_ROUTES = [
    ("GET", "/api/health"),
    ("GET", "/api/items"),
    ("POST", "/api/items"),
    ("POST", "/api/feedback"),
]

DEFAULT_PIPELINE_STAGES = [
    "ingest",
    "validate",
    "dedupe",
    "aggregate",
]

VALID_STATUSES = ("draft", "scaffolding", "running", "retired")


@dataclass
class Prototype:
    """A scaffolded prototype built from one idea brief."""

    slug: str
    idea_slug: str
    name: str
    status: str = "draft"
    api_routes: list = field(default_factory=list)
    pipeline_stages: list = field(default_factory=list)
    frontend_page: str = ""
    build_minutes: int = 0


class PrototypeStore:
    """In-memory registry of scaffolded prototypes."""

    def __init__(self):
        self._prototypes = {}

    def scaffold(self, idea, name=None, build_minutes=0):
        """Generate a prototype from an idea brief.

        Raises ValueError when the idea is missing, already has a live
        prototype, or the build time is not a plausible rapid-prototype
        number (a prototype that takes weeks is not a prototype).
        """
        if idea is None:
            raise ValueError("cannot scaffold a prototype without an idea brief")
        if idea.slug in self._prototypes:
            existing = self._prototypes[idea.slug]
            if existing.status != "retired":
                raise ValueError(f"idea {idea.slug!r} already has a live prototype")
        if not isinstance(build_minutes, int) or build_minutes < 1:
            raise ValueError("build_minutes must be a positive number of minutes")
        if build_minutes > 60 * 24 * 5:
            raise ValueError("build_minutes over 5 days is not rapid prototyping")
        proto = Prototype(
            slug=f"{idea.slug}-v1",
            idea_slug=idea.slug,
            name=name or idea.title,
            status="scaffolding",
            api_routes=[{"method": m, "path": p} for m, p in DEFAULT_API_ROUTES],
            pipeline_stages=list(DEFAULT_PIPELINE_STAGES),
            frontend_page=f"/prototypes/{idea.slug}",
            build_minutes=build_minutes,
        )
        self._prototypes[idea.slug] = proto
        return proto

    def get(self, idea_slug):
        return self._prototypes.get(idea_slug)

    def list(self, status=None):
        protos = sorted(self._prototypes.values(), key=lambda p: p.slug)
        if status is not None:
            protos = [p for p in protos if p.status == status]
        return protos

    def set_status(self, idea_slug, status):
        proto = self.get(idea_slug)
        if proto is None:
            raise ValueError(f"unknown prototype for idea {idea_slug!r}")
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        proto.status = status
        return proto

    def launch(self, idea_slug):
        """Move a scaffolded prototype to running — the moment real users can use it."""
        proto = self.get(idea_slug)
        if proto is None:
            raise ValueError(f"unknown prototype for idea {idea_slug!r}")
        if proto.status != "scaffolding":
            raise ValueError(f"only a scaffolding prototype can launch (now {proto.status})")
        proto.status = "running"
        return proto
