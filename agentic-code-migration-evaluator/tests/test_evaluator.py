"""Tests for the migration evaluator."""

from migration_evaluator.evaluator import MigrationEvaluator
from migration_evaluator.samples import SAMPLES
from migration_evaluator.transforms import migrate_source


def test_reference_migration_passes_every_sample():
    for name, sample in SAMPLES.items():
        report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
            migrate_source(sample.legacy_source), name
        )
        assert report.passed, (name, report.invariant_failures)


def test_broken_migration_fails_behaviour():
    sample = SAMPLES["counters"]
    broken = sample.legacy_source.replace("total += i", "total += 1")
    report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
        broken, sample.name
    )
    assert report.behaviour_score < 1.0
    assert report.passed_cases < report.total_cases
    assert not report.passed


def test_missing_function_is_invariant_failure():
    sample = SAMPLES["greeting"]
    dropped = "def greet(name):\n    return 'Hello, ' + name + '!'\n"
    report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
        dropped, sample.name
    )
    assert not report.invariants_ok
    assert any("shout" in f for f in report.invariant_failures)


def test_leftover_legacy_idiom_flagged():
    sample = SAMPLES["counters"]
    report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
        sample.legacy_source, sample.name
    )
    assert "xrange(" in report.leftover_legacy
    assert not report.invariants_ok


def test_syntax_error_in_migration_fails():
    sample = SAMPLES["greeting"]
    report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
        "def greet(:\n", sample.name
    )
    assert not report.invariants_ok
    assert report.passed_cases == 0


def test_overall_score_weights_behaviour_over_hygiene():
    sample = SAMPLES["lookup"]
    # Correct behaviour, but a leftover legacy idiom survives in a comment:
    # behaviour 1.0, hygiene 0, so overall is 0.7.
    migrated = migrate_source(sample.legacy_source) + "# kept xrange( note\n"
    report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
        migrated, sample.name
    )
    assert report.behaviour_score == 1.0
    assert report.overall_score == 0.7
