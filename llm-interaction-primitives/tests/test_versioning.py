"""Tests for versioning, deprecation, and changelog entries."""

import warnings

import pytest

from interaction_lib import bump_version, changelog_entry, deprecated, parse_version


def test_parse_version():
    assert parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_version("1.2")


def test_bump_version():
    assert bump_version("1.2.3", "patch") == "1.2.4"
    assert bump_version("1.2.3", "minor") == "1.3.0"
    assert bump_version("1.2.3", "major") == "2.0.0"


def test_bump_version_rejects_unknown_part():
    with pytest.raises(ValueError):
        bump_version("1.2.3", "mega")


def test_deprecated_warns_and_still_runs():
    @deprecated("1.0.0", replacement="new_render", removed_in="2.0.0")
    def old_render():
        return "ok"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert old_render() == "ok"
    assert len(caught) == 1
    assert issubclass(caught[0].category, DeprecationWarning)
    assert "new_render" in str(caught[0].message)


def test_changelog_entry():
    entry = changelog_entry("1.1.0", ["Added rollout loop.", "Fixed tokenizer round trip."])
    assert entry.startswith("## 1.1.0\n")
    assert "- Added rollout loop." in entry


def test_changelog_entry_rejects_bad_version():
    with pytest.raises(ValueError):
        changelog_entry("v1", ["Nope."])
