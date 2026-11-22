"""Semantic versioning helpers and deprecation support for the library."""
import re
import warnings

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(version)
    if not match:
        raise ValueError(f"not a semantic version: '{version}'")
    return tuple(int(g) for g in match.groups())


def bump(version: str, part: str) -> str:
    major, minor, patch = parse(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump part '{part}'")


def deprecated(since: str, replacement: str | None = None):
    """Mark a function deprecated; calls emit a DeprecationWarning."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            msg = f"{fn.__name__} is deprecated since {since}"
            if replacement:
                msg += f"; use {replacement} instead"
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator
