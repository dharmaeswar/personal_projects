"""Dependency packaging: manifest parsing, version resolution, bundle build.

The packager turns a handler file plus a requirements-style manifest into a
deployment bundle: it resolves each pinned requirement against a small
deterministic index, copies the handler and the resolved dependency files
into the bundle directory, precompiles every .py file to .pyc at build time
(so import time at runtime is not spent compiling), and enforces a total
size budget. A bundle over budget is rejected, not silently shipped.
"""

import json
import os
import py_compile
import shutil
from pathlib import Path

# Deterministic stand-in for a package index: name -> {version: size_bytes}.
# Real runtimes resolve against PyPI; this index keeps the demo offline and
# reproducible while exercising the same resolution and budgeting logic.
FAKE_INDEX = {
    "requests": {"2.32.3": 512_000, "2.31.0": 498_000},
    "pydantic": {"2.9.2": 1_240_000, "2.7.4": 1_180_000},
    "numpy": {"2.1.2": 18_400_000, "1.26.4": 16_900_000},
    "boto3": {"1.35.0": 3_900_000, "1.34.0": 3_800_000},
    "fastapi": {"0.115.0": 860_000, "0.111.0": 820_000},
}


class PackagingError(ValueError):
    """Raised when a manifest cannot be parsed or resolved."""


class BundleTooLarge(PackagingError):
    """Raised when a bundle exceeds its configured size budget."""


def parse_requirements(text: str) -> list[tuple[str, str]]:
    """Parse a requirements-style manifest into (name, spec) pairs.

    Supports ``name``, ``name==x.y.z`` and ``name>=x.y.z``. Blank lines and
    ``#`` comments are ignored. Anything else raises PackagingError.
    """
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            name, spec = line.split("==", 1)
            spec = "==" + spec.strip()
        elif ">=" in line:
            name, spec = line.split(">=", 1)
            spec = ">=" + spec.strip()
        elif any(c in line for c in "<>~! "):
            raise PackagingError(f"unsupported requirement line: {raw!r}")
        else:
            name, spec = line, ""
        name = name.strip().lower()
        if not name:
            raise PackagingError(f"empty requirement line: {raw!r}")
        out.append((name, spec))
    return out


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split(".") if p.isdigit())


def resolve(name: str, spec: str) -> tuple[str, int]:
    """Resolve one requirement against FAKE_INDEX; return (version, size)."""
    versions = FAKE_INDEX.get(name)
    if versions is None:
        raise PackagingError(f"unknown package {name!r} (not in the index)")
    candidates = sorted(versions, key=_version_key)
    if spec.startswith("=="):
        wanted = spec[2:]
        if wanted not in versions:
            raise PackagingError(f"{name}=={wanted} is not in the index")
        return wanted, versions[wanted]
    if spec.startswith(">="):
        floor = _version_key(spec[2:])
        for version in reversed(candidates):
            if _version_key(version) >= floor:
                return version, versions[version]
        raise PackagingError(f"no {name} version satisfies {spec}")
    if spec == "":
        return candidates[-1], versions[candidates[-1]]
    raise PackagingError(f"unsupported spec {spec!r} for {name!r}")


def precompile(tree: Path) -> int:
    """Byte-compile every .py file under tree; return the file count."""
    count = 0
    for py_file in sorted(tree.rglob("*.py")):
        py_compile.compile(str(py_file), cfile=str(py_file) + "c", doraise=True)
        count += 1
    return count


def build_bundle(
    handler_path: str | Path,
    requirements_text: str,
    out_dir: str | Path,
    size_budget_mb: int = 250,
) -> dict:
    """Build a deployment bundle; return its manifest dict.

    The bundle contains the handler, one placeholder file per resolved
    dependency (standing in for the installed package files), and a
    manifest.json describing versions, sizes, and precompilation. Raises
    BundleTooLarge when the total size exceeds the budget.
    """
    handler = Path(handler_path)
    if not handler.is_file():
        raise PackagingError(f"handler not found: {handler}")
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    resolved = []
    total_bytes = 0
    for name, spec in parse_requirements(requirements_text):
        version, size = resolve(name, spec)
        dep_dir = out / "deps" / name
        dep_dir.mkdir(parents=True)
        # Placeholder for the installed package: a real packager copies the
        # site-packages files; here one file of the indexed size stands in.
        with open(dep_dir / f"{name}-{version}.dist", "wb") as fh:
            fh.write(b"\0" * size)
        resolved.append({"name": name, "version": version, "size_bytes": size})
        total_bytes += size

    shutil.copy2(handler, out / handler.name)
    total_bytes += handler.stat().st_size
    compiled = precompile(out)

    budget_bytes = size_budget_mb * 1024 * 1024
    if total_bytes > budget_bytes:
        shutil.rmtree(out)
        raise BundleTooLarge(
            f"bundle is {total_bytes} bytes, over the "
            f"{budget_bytes} byte budget ({size_budget_mb} MB)"
        )

    manifest = {
        "handler": handler.name,
        "dependencies": resolved,
        "total_bytes": total_bytes,
        "size_budget_bytes": budget_bytes,
        "precompiled_files": compiled,
        "within_budget": total_bytes <= budget_bytes,
    }
    with open(out / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest
