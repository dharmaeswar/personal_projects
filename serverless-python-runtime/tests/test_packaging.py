import json

import pytest

from runtime.packaging import (
    BundleTooLarge,
    PackagingError,
    build_bundle,
    parse_requirements,
    resolve,
)


def test_parse_requirements_skips_comments_and_blanks():
    parsed = parse_requirements("# comment\nrequests==2.32.3\n\npydantic>=2.7.0\nnumpy\n")
    assert parsed == [
        ("requests", "==2.32.3"),
        ("pydantic", ">=2.7.0"),
        ("numpy", ""),
    ]


def test_parse_requirements_rejects_unsupported_lines():
    with pytest.raises(PackagingError):
        parse_requirements("requests~=2.0")


def test_resolve_exact_version():
    assert resolve("requests", "==2.32.3") == ("2.32.3", 512_000)


def test_resolve_floor_picks_newest_above_floor():
    assert resolve("pydantic", ">=2.7.0")[0] == "2.9.2"


def test_resolve_unpinned_picks_newest():
    assert resolve("requests", "")[0] == "2.32.3"


def test_resolve_unknown_package():
    with pytest.raises(PackagingError):
        resolve("not-a-real-package", "")


def test_resolve_missing_version():
    with pytest.raises(PackagingError):
        resolve("requests", "==9.9.9")


def test_build_bundle_writes_manifest_and_precompiles(tmp_path):
    handler = tmp_path / "handler.py"
    handler.write_text("def handle(event):\n    return {'ok': True}\n")
    bundle = tmp_path / "bundle"
    manifest = build_bundle(handler, "requests==2.32.3", bundle, size_budget_mb=250)
    assert manifest["within_budget"] is True
    assert manifest["dependencies"] == [
        {"name": "requests", "version": "2.32.3", "size_bytes": 512_000}
    ]
    assert manifest["precompiled_files"] >= 1
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "handler.py").is_file()
    assert (bundle / "handler.pyc").is_file()
    stored = json.loads((bundle / "manifest.json").read_text())
    assert stored["total_bytes"] == manifest["total_bytes"]


def test_build_bundle_rejects_oversize(tmp_path):
    handler = tmp_path / "handler.py"
    handler.write_text("def handle(event):\n    return {}\n")
    # numpy alone is ~18 MB, over a 1 MB budget.
    with pytest.raises(BundleTooLarge):
        build_bundle(handler, "numpy==2.1.2", tmp_path / "bundle", size_budget_mb=1)


def test_build_bundle_missing_handler(tmp_path):
    with pytest.raises(PackagingError):
        build_bundle(tmp_path / "nope.py", "", tmp_path / "bundle")
