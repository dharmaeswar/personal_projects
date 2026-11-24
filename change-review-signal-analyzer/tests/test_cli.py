"""Tests for the command-line interface."""

import json
import subprocess
import sys
from pathlib import Path

from test_signals import CLEAN_DIFF, EVAL_DIFF


def _run_cli(diff_text: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    diff_file = Path(__file__).parent / "_tmp_cli.diff"
    diff_file.write_text(diff_text, encoding="utf-8")
    try:
        return subprocess.run(
            [sys.executable, "-m", "changereview.cli", "analyze", str(diff_file)]
            + (extra_args or []),
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
    finally:
        diff_file.unlink(missing_ok=True)


def test_cli_markdown_output_for_clean_change():
    result = _run_cli(CLEAN_DIFF)
    assert result.returncode == 0
    assert "APPROVE" in result.stdout


def test_cli_blocks_on_eval_with_exit_code_2():
    result = _run_cli(EVAL_DIFF)
    assert result.returncode == 2
    assert "BLOCK" in result.stdout


def test_cli_json_output_parses():
    result = _run_cli(CLEAN_DIFF, ["--format", "json"])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "APPROVE"
    assert payload["risk_score"] == 0
