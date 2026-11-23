"""Tests for build-metadata / lint checks."""

from pkgtool.checks import run_checks


def _pkg(tmp_path, files):
    root = tmp_path / "sample"
    root.mkdir()
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def _by_code(results):
    return {r.code: r for r in results}


def test_metadata_present_ok(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "README.md": "# sample\n",
    })
    by = _by_code(run_checks(root))
    assert by["PKG001"].level == "ok"
    assert by["PKG002"].level == "ok"
    assert by["PKG003"].level == "ok"


def test_metadata_missing_errors(tmp_path):
    root = _pkg(tmp_path, {"__init__.py": ""})
    by = _by_code(run_checks(root))
    assert by["PKG001"].level == "error"
    assert by["PKG002"].level == "warning"
    assert by["PKG011"].level == "warning"


def test_missing_init_flagged(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "sub/mod.py": "x = 1\n",
    })
    by = _by_code(run_checks(root))
    assert by["PKG010"].level == "error"


def test_unused_import_flagged(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "mod.py": "import os\nimport sys\n\ndef f():\n    return sys.version\n",
    })
    results = run_checks(root)
    unused = [r for r in results if r.code == "PKG021"]
    assert len(unused) == 1
    assert "os" in unused[0].message


def test_wildcard_import_flagged(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "mod.py": "from os import *\n",
    })
    results = run_checks(root)
    assert any(r.code == "PKG020" and r.level == "warning" for r in results)


def test_clean_source_ok(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "pyproject.toml": "[project]\nname = 'sample'\n",
        "README.md": "# sample\n",
        "mod.py": "import os\n\ndef f():\n    return os.getcwd()\n",
        "tests/test_mod.py": "def test_x():\n    assert True\n",
    })
    by = _by_code(run_checks(root))
    assert by["PKG020"].level == "ok"
    assert by["PKG011"].level == "ok"
    assert not any(r.level == "error" for r in run_checks(root))
