"""Graders and reward functions for rollout evaluation.

Each grader returns a score in [0, 1] plus a short reason. Graders are
pure functions so they compose: a rollout can be scored by several
graders and the scores averaged or thresholded.
"""


def exact_match(expected: str, actual: str) -> dict:
    match = expected.strip() == actual.strip()
    return {"score": 1.0 if match else 0.0,
            "reason": "exact match" if match else "text differs"}


def regex_match(pattern: str, actual: str) -> dict:
    import re
    match = re.search(pattern, actual) is not None
    return {"score": 1.0 if match else 0.0,
            "reason": f"pattern {'found' if match else 'not found'}: {pattern}"}


def keyword_coverage(keywords: list[str], actual: str) -> dict:
    if not keywords:
        raise ValueError("keyword list must not be empty")
    lowered = actual.lower()
    found = [k for k in keywords if k.lower() in lowered]
    return {"score": len(found) / len(keywords),
            "reason": f"{len(found)}/{len(keywords)} keywords present"}


def numeric_close(expected: float, actual: float, tolerance: float) -> dict:
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    ok = abs(expected - actual) <= tolerance
    return {"score": 1.0 if ok else 0.0,
            "reason": f"|{expected} - {actual}| {'<=' if ok else '>'} {tolerance}"}


def combine(results: list[dict], weights: list[float] | None = None) -> dict:
    """Weighted mean of grader results (equal weights by default)."""
    if not results:
        raise ValueError("no grader results to combine")
    if weights is None:
        weights = [1.0] * len(results)
    if len(weights) != len(results):
        raise ValueError("weights must match results")
    total = sum(weights)
    score = sum(r["score"] * w for r, w in zip(results, weights)) / total
    return {"score": score,
            "reason": "; ".join(r["reason"] for r in results)}
