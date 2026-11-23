"""Tests for public API-surface extraction."""

from pkgtool.api import extract_api_surface


def _pkg(tmp_path, files):
    root = tmp_path / "sample"
    root.mkdir()
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_public_members(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "mod.py": (
            "VERSION = '1.0'\n"
            "def run():\n    pass\n"
            "class Worker:\n    pass\n"
            "def _private():\n    pass\n"
            "_hidden = 1\n"
        ),
    })
    surface = extract_api_surface(root)
    assert surface["mod"].public_names == ["VERSION", "run", "Worker"]
    assert surface["mod"].has_all is False


def test_all_honored(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "mod.py": (
            "def _internal():\n    pass\n"
            "def public():\n    pass\n"
            "__all__ = ['_internal']\n"
        ),
    })
    surface = extract_api_surface(root)
    assert surface["mod"].public_names == ["_internal"]
    assert surface["mod"].has_all is True


def test_empty_module(tmp_path):
    root = _pkg(tmp_path, {"__init__.py": "", "mod.py": ""})
    surface = extract_api_surface(root)
    assert surface["mod"].public_names == []
