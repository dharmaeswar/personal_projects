"""Parse unified diffs into structured changed-file records.

Only the standard unified-diff shape is handled: ``diff --git`` headers,
``---``/``+++`` file lines, ``@@`` hunk headers, and ``+``/``-``/context
lines. Anything else is ignored, so a malformed diff yields an empty
result instead of an exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Hunk:
    """One hunk of a unified diff, with new-file line numbers tracked."""

    old_start: int
    new_start: int
    added_lines: list[tuple[int, str]] = field(default_factory=list)
    removed_lines: list[tuple[int, str]] = field(default_factory=list)

    @property
    def added_count(self) -> int:
        return len(self.added_lines)

    @property
    def removed_count(self) -> int:
        return len(self.removed_lines)


@dataclass
class ChangedFile:
    """One file touched by a diff, with its added and removed lines."""

    path: str
    is_new: bool = False
    is_deleted: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def added_lines(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for hunk in self.hunks:
            out.extend(hunk.added_lines)
        return out

    @property
    def removed_lines(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for hunk in self.hunks:
            out.extend(hunk.removed_lines)
        return out

    @property
    def added_count(self) -> int:
        return len(self.added_lines)

    @property
    def removed_count(self) -> int:
        return len(self.removed_lines)

    @property
    def is_test_file(self) -> bool:
        lowered = self.path.lower()
        return (
            lowered.startswith("test_")
            or "/test_" in lowered
            or lowered.endswith("_test.py")
            or "/tests/" in lowered
            or lowered.startswith("tests/")
        )


def _strip_prefix(path: str) -> str:
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def parse_diff(diff_text: str) -> list[ChangedFile]:
    """Parse unified diff text into a list of ChangedFile records."""
    files: list[ChangedFile] = []
    current: ChangedFile | None = None
    current_hunk: Hunk | None = None
    new_lineno = 0
    pending_new = False

    for raw in diff_text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("diff --git "):
            current = None
            current_hunk = None
            pending_new = False
            continue
        if line.startswith("--- "):
            if current is not None:
                current.is_deleted = line[4:].strip() != "/dev/null"
            continue
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                if current is not None:
                    current.is_deleted = True
                continue
            path = _strip_prefix(target)
            if current is None or current.path != path:
                current = ChangedFile(path=path, is_new=pending_new)
                files.append(current)
            current_hunk = None
            pending_new = False
            continue
        if line.startswith("new file mode"):
            pending_new = True
            continue
        match = _HUNK_RE.match(line)
        if match:
            old_start = int(match.group(1))
            new_start = int(match.group(3))
            current_hunk = Hunk(old_start=old_start, new_start=new_start)
            if current is not None:
                current.hunks.append(current_hunk)
            new_lineno = new_start
            continue
        if current is None or current_hunk is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.added_lines.append((new_lineno, line[1:]))
            new_lineno += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.removed_lines.append((new_lineno, line[1:]))
        elif line.startswith("\\"):
            continue
        else:
            # Context line (or an empty line): advances the new-file cursor.
            new_lineno += 1
    return files
