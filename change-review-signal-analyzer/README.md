# Change Review Signal Analyzer

A portfolio project for a change-review / developer-tooling role (Amazon's
Change Review team style). It models the core problem of that team: given a
code change, surface the signals a reviewer needs before approving it —
change size, risky patterns, test coverage of the changed lines, and who
should review it — and turn those signals into a verdict.

**All data is synthetic and local.** No real repository, review system, or
CI service is involved, and nothing here is a claim about any real company's
systems.

## What it does

- **Diff parsing** (`changereview/diffparse.py`) — parses unified diffs into
  changed files with added/removed lines and new-file line numbers; detects
  test files.
- **Signal detectors** (`changereview/signals.py`) — scans added lines for
  blocking patterns (hardcoded credentials, `eval()` / `exec()` /
  `os.system()`), warning patterns (TODO/FIXME, bare `except`, string-built
  SQL, debug prints), large changes (400+ added lines or 10+ files),
  uncovered added lines from a coverage map, and source files changed with
  no test file alongside them.
- **Review verdicts** (`changereview/review.py`) — BLOCK on any blocking
  finding, NEEDS_REVIEW on large changes, low coverage, warnings, or missing
  tests, APPROVE otherwise; a transparent 0–100 risk score where every point
  comes from a named signal; reviewer suggestions from a longest-prefix
  ownership map.
- **Reports** (`changereview/report.py`) — Markdown for a human reviewer and
  JSON for a bot.
- **CLI** (`changereview/cli.py`) — `python -m changereview.cli analyze
  <diff-file> [--coverage coverage.json] [--owners owners.json]
  [--format md|json]`; exit code 2 when the verdict is BLOCK.

## Run it

```bash
pip install -r requirements.txt   # pytest only
python -m pytest -q               # 25 tests
python run_demo.py                # sample change with a secret in it
```

The demo reviews a three-line change that adds a TODO, a hardcoded API key,
and a string-built SQL query. Coverage covers 1 of the 3 added lines, and the
payments team owns the file. Expected output: verdict **BLOCK**, risk score
85/100 (40 blocking + 20 warnings + 15 low coverage + 10 no tests in the
change), reviewers payments-team and priya.

## Skills used

Only skills Dharma has verified: Python, PyTest, Git, Linux, code review,
CI/CD, REST APIs, JSON. This project does **not** claim production
code-review, static-analysis, or AWS service experience.
