"""Tests for import-graph construction."""

from pkgtool.graph import build_graph, module_name


def _pkg(tmp_path, files):
    root = tmp_path / "sample"
    root.mkdir()
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_graph_edges_and_modules(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import b\nimport os\n",
        "b.py": "from .c import helper\n",
        "c.py": "def helper():\n    return 1\n",
    })
    g = build_graph(root)
    assert g.package == "sample"
    assert g.modules == {"a", "b", "c"}
    assert g.edges["a"] == {"b"}
    assert g.edges["b"] == {"c"}
    assert g.edges.get("c", set()) == set()
    assert g.external["a"] == {"os"}


def test_graph_subpackage_and_absolute_import(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "core.py": "from sample.util import fmt\n",
        "util.py": "def fmt(x):\n    return str(x)\n",
        "sub/__init__.py": "from ..core import run\n",
        "sub/work.py": "from sample import core\n",
    })
    g = build_graph(root)
    assert "sub" in g.modules and "sub.work" in g.modules
    assert g.edges["core"] == {"util"}
    assert g.edges["sub"] == {"core"}
    assert g.edges["sub.work"] == {"core"}


def test_graph_leaves_and_roots(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import b\n",
        "b.py": "",
    })
    g = build_graph(root)
    assert g.leaves() == {"b"}
    assert g.roots() == {"a"}
    assert g.dependents("b") == {"a"}


def test_module_name_init_and_nested(tmp_path):
    root = tmp_path / "pkg"
    assert module_name(root, root / "__init__.py") == ""
    assert module_name(root, root / "sub" / "__init__.py") == "sub"
    assert module_name(root, root / "sub" / "mod.py") == "sub.mod"


def test_graph_rejects_missing_dir(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        build_graph(tmp_path / "nope")
