"""Tests for the unified-diff parser."""

from changereview.diffparse import parse_diff

SIMPLE_DIFF = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import json
 def main():
-    print("old")
+    print("new")
"""

NEW_FILE_DIFF = """diff --git a/src/new.py b/src/new.py
new file mode 100644
--- /dev/null
+++ b/src/new.py
@@ -0,0 +1,2 @@
+def hello():
+    return "hi"
"""

MULTI_DIFF = SIMPLE_DIFF + """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1,1 +1,2 @@
 def test_main():
+    assert True
"""


def test_parses_one_file_with_added_and_removed_lines():
    files = parse_diff(SIMPLE_DIFF)
    assert len(files) == 1
    assert files[0].path == "src/app.py"
    assert files[0].added_count == 2
    assert files[0].removed_count == 1
    assert files[0].added_lines[0] == (2, "import json")
    assert files[0].added_lines[1] == (4, '    print("new")')


def test_new_file_flag_and_line_numbers():
    files = parse_diff(NEW_FILE_DIFF)
    assert len(files) == 1
    assert files[0].is_new
    assert files[0].added_lines == [(1, "def hello():"), (2, '    return "hi"')]


def test_multiple_files_and_test_detection():
    files = parse_diff(MULTI_DIFF)
    assert len(files) == 2
    assert not files[0].is_test_file
    assert files[1].is_test_file
    assert files[1].path == "tests/test_app.py"


def test_empty_diff_returns_no_files():
    assert parse_diff("") == []
    assert parse_diff("not a diff at all\n") == []


def test_context_lines_advance_line_numbers():
    diff = """diff --git a/src/x.py b/src/x.py
--- a/src/x.py
+++ b/src/x.py
@@ -10,4 +10,5 @@
 line one
 line two
+line three
 line four
"""
    files = parse_diff(diff)
    assert files[0].added_lines == [(12, "line three")]
