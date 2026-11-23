"""Tests for dependency-cycle detection."""

from pkgtool.cycles import find_cycles
from pkgtool.graph import build_graph


def _pkg(tmp_path, files):
    root = tmp_path / "sample"
    root.mkdir()
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_no_cycles(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import b\n",
        "b.py": "from . import c\n",
        "c.py": "",
    })
    assert find_cycles(build_graph(root)) == []


def test_simple_cycle(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import b\n",
        "b.py": "from . import a\n",
    })
    cycles = find_cycles(build_graph(root))
    assert len(cycles) == 1
    assert set(cycles[0]) == {"a", "b"}
    assert cycles[0][0] == cycles[0][-1] or len(cycles[0]) == 2


def test_three_module_cycle(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import b\n",
        "b.py": "from . import c\n",
        "c.py": "from . import a\n",
        "d.py": "",
    })
    cycles = find_cycles(build_graph(root))
    assert len(cycles) == 1
    assert set(cycles[0]) == {"a", "b", "c"}


def test_self_import_cycle(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import a\n",
    })
    assert find_cycles(build_graph(root)) == [["a"]]


def test_two_independent_cycles(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import b\n",
        "b.py": "from . import a\n",
        "x.py": "from . import y\n",
        "y.py": "from . import x\n",
    })
    cycles = find_cycles(build_graph(root))
    assert len(cycles) == 2
    assert {frozenset(c) for c in cycles} == {frozenset({"a", "b"}), frozenset({"x", "y"})}
