"""Tests for the samples and the CLI runner."""

import subprocess
import sys

from migration_evaluator.samples import SAMPLES
from migration_evaluator.transforms import migrate_source


def test_samples_have_cases_and_parse():
    assert len(SAMPLES) == 3
    for sample in SAMPLES.values():
        assert sample.cases, sample.name
        compile(sample.legacy_source, "<test>", "exec")


def test_reference_migration_changes_each_sample():
    for sample in SAMPLES.values():
        assert migrate_source(sample.legacy_source) != sample.legacy_source


def test_cli_runner_exits_zero():
    result = subprocess.run(
        [sys.executable, "run_evaluation.py"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
