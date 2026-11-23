"""Tests for the pkgtool CLI."""

import json

from pkgtool.cli import main


def _pkg(tmp_path, files):
    root = tmp_path / "sample"
    root.mkdir()
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_cli_cycles_clean(tmp_path, capsys):
    root = _pkg(tmp_path, {"__init__.py": "", "a.py": "from . import b\n", "b.py": ""})
    assert main(["cycles", str(root)]) == 0
    assert "no dependency cycles" in capsys.readouterr().out


def test_cli_cycles_found(tmp_path, capsys):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "a.py": "from . import b\n",
        "b.py": "from . import a\n",
    })
    assert main(["cycles", str(root)]) == 1
    assert "a -> b -> a" in capsys.readouterr().out


def test_cli_api(tmp_path, capsys):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "mod.py": "def run():\n    pass\n",
    })
    assert main(["api", str(root)]) == 0
    assert "mod: run" in capsys.readouterr().out


def test_cli_analyze_json(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "README.md": "# sample\n",
        "a.py": "from . import b\n",
        "b.py": "",
    })
    out = tmp_path / "report.json"
    assert main(["analyze", str(root), "--format", "json", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["package"] == "sample"
    assert data["cycles"] == []
    assert data["edges"]["a"] == ["b"]


def test_cli_analyze_text_with_cycle(tmp_path, capsys):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "a.py": "from . import b\n",
        "b.py": "from . import a\n",
    })
    assert main(["analyze", str(root)]) == 1
    out = capsys.readouterr().out
    assert "Dependency cycles:" in out
    assert "a -> b -> a" in out


def test_cli_check_clean(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "README.md": "# sample\n",
        "mod.py": "x = 1\n",
    })
    assert main(["check", str(root)]) == 0
