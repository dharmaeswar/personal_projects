"""Release-gate decision from a pytest result summary.

The gate takes the counts a CI job already has (passed, failed, skipped,
errored, plus the names of the required checks that must have passed) and
applies three rules:

1. No failures or errors at all.
2. Pass rate at or above ``min_pass_rate`` (default 1.0 — everything passes).
3. Every required check name appears in the passed list.

The returned report is a plain dict so it can be dumped to JSON and read
by the next CI step. ``decide`` never raises on odd input: a summary with
no tests at all fails the gate with a clear reason.
"""
import json


def decide(summary, min_pass_rate=1.0, required_checks=()):
    """Decide PASS/FAIL for one release candidate.

    ``summary`` is a dict with integer keys ``passed``, ``failed``,
    ``skipped``, ``error`` and a ``passed_names`` list of test node ids
    that passed. Returns a report dict with ``verdict`` ("PASS"/"FAIL"),
    the counts, the pass rate, and a ``reasons`` list (empty on PASS).
    """
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    skipped = int(summary.get("skipped", 0))
    error = int(summary.get("error", 0))
    total = passed + failed + skipped + error
    passed_names = set(summary.get("passed_names", []))
    reasons = []
    if total == 0:
        reasons.append("no tests ran")
    if failed:
        reasons.append(f"{failed} test(s) failed")
    if error:
        reasons.append(f"{error} test(s) errored")
    if total > 0:
        pass_rate = passed / total
        if pass_rate < min_pass_rate:
            reasons.append(
                f"pass rate {pass_rate:.2%} below minimum {min_pass_rate:.2%}")
    else:
        pass_rate = 0.0
    missing = [c for c in required_checks if c not in passed_names]
    if missing:
        reasons.append(f"required checks did not pass: {missing}")
    verdict = "PASS" if not reasons else "FAIL"
    return {
        "verdict": verdict,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "error": error,
        "total": total,
        "pass_rate": round(pass_rate, 4),
        "min_pass_rate": min_pass_rate,
        "required_checks": list(required_checks),
        "reasons": reasons,
    }


def report_json(report):
    """Serialize a gate report dict to indented JSON text."""
    return json.dumps(report, indent=2, sort_keys=True)
