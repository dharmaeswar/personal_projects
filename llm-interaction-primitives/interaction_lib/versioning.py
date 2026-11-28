"""Semantic versioning, deprecation policy, and changelog entries.

A public library needs a version contract: ``parse_version`` and
``bump_version`` implement strict ``MAJOR.MINOR.PATCH`` handling,
``@deprecated`` marks a public function as going away in a stated version
(and warns on every call, so users notice before it breaks), and
``changelog_entry`` formats a release note entry. Nothing here is silent:
bad versions raise, and deprecated calls warn.
"""

from __future__ import annotations

import functools
import re
import warnings
from collections.abc import Callable
from typing import TypeVar

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

F = TypeVar("F", bound=Callable)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse ``MAJOR.MINOR.PATCH`` into a tuple. Raises ValueError otherwise."""
    match = _VERSION_RE.match(version.strip())
    if match is None:
        raise ValueError(f"not a semantic version: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(version: str, part: str = "patch") -> str:
    """Bump one part of a semantic version; lower parts reset to zero."""
    major, minor, patch = parse_version(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump part {part!r}; expected major, minor, or patch")


def deprecated(since: str, replacement: str | None = None, removed_in: str | None = None) -> Callable[[F], F]:
    """Mark a public function deprecated; calls emit a DeprecationWarning."""

    def decorator(func: F) -> F:
        message = f"{func.__name__} is deprecated since {since}"
        if replacement:
            message += f"; use {replacement} instead"
        if removed_in:
            message += f"; will be removed in {removed_in}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def changelog_entry(version: str, changes: list[str]) -> str:
    """Format a markdown changelog entry for a release."""
    parse_version(version)  # validates the version string
    lines = [f"## {version}", ""]
    lines.extend(f"- {change}" for change in changes)
    return "\n".join(lines) + "\n"
