"""Tests for the change-signal detectors."""

from changereview.diffparse import parse_diff
from changereview.signals import analyze_change

SECRET_DIFF = """diff --git a/src/config.py b/src/config.py
--- a/src/config.py
+++ b/src/config.py
@@ -1,1 +1,2 @@
 key = "old"
+api_key = "sk-live-1234567890"
"""

EVAL_DIFF = """diff --git a/src/run.py b/src/run.py
--- a/src/run.py
+++ b/src/run.py
@@ -1,1 +1,2 @@
 import os
+eval(user_input)
"""

TODO_DIFF = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 def run():
+    # TODO: handle retries
     pass
"""

SQL_DIFF = """diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -1,2 +1,3 @@
 def get_user(name):
+    query = "select * from users where name = '" + name + "'"
     return query
"""

CLEAN_DIFF = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 def run():
+    return 42
     pass
diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1,1 +1,2 @@
 def test_run():
+    assert run() == 42
"""


def test_hardcoded_secret_is_blocking():
    signals = analyze_change(parse_diff(SECRET_DIFF))
    assert len(signals.blocking_findings) == 1
    assert signals.blocking_findings[0].category == "hardcoded credential"


def test_eval_is_blocking():
    signals = analyze_change(parse_diff(EVAL_DIFF))
    assert [f.category for f in signals.blocking_findings] == ["eval() call"]


def test_todo_is_warning_not_blocking():
    signals = analyze_change(parse_diff(TODO_DIFF))
    assert signals.blocking_findings == []
    assert len(signals.warning_findings) == 1
    assert "TODO" in signals.warning_findings[0].category


def test_string_built_sql_is_warning():
    signals = analyze_change(parse_diff(SQL_DIFF))
    assert any(f.category == "string-built SQL query" for f in signals.warning_findings)


def test_clean_change_has_no_findings():
    signals = analyze_change(parse_diff(CLEAN_DIFF))
    assert signals.findings == []
    assert signals.files_changed == 2
    assert signals.lines_added == 2


def test_coverage_gap_lists_uncovered_added_lines():
    coverage = {"src/app.py": {1}, "tests/test_app.py": {1, 2}}  # added line 2 in app.py is not covered
    signals = analyze_change(parse_diff(CLEAN_DIFF), coverage=coverage)
    assert signals.uncovered_added_lines == {"src/app.py": [2]}
    assert signals.coverage_ratio == 0.5


def test_source_without_tests_is_flagged():
    signals = analyze_change(parse_diff(TODO_DIFF))
    assert signals.source_files_without_tests == ["src/app.py"]
    signals_clean = analyze_change(parse_diff(CLEAN_DIFF))
    assert signals_clean.source_files_without_tests == []


def test_large_change_flag():
    added = "\n".join(f"+line {i}" for i in range(450))
    diff = (
        "diff --git a/src/big.py b/src/big.py\n"
        "--- a/src/big.py\n+++ b/src/big.py\n@@ -1,1 +1,451 @@\n"
        " first\n" + added + "\n"
    )
    signals = analyze_change(parse_diff(diff))
    assert signals.is_large
    assert any(f.category == "large change" for f in signals.findings)
