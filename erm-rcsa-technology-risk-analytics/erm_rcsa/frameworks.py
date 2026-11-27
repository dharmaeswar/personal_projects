"""1LOD framework assessments: COBIT / NIST / ITIL / DCAM / DMBOK coverage.

An assessment maps each framework requirement to Met / Partial / Not Met
for a 1LOD function; coverage is the weight-weighted share of Met items.
"""

from __future__ import annotations

VALID = {"Met", "Partial", "Not Met"}


def assess(requirements, results):
    """requirements: list of FrameworkRequirement. results: {req_id: status}.

    Returns per-framework and per-function coverage plus the open gaps.
    Unknown requirement ids and invalid statuses raise ValueError.
    """
    for req_id, status in results.items():
        if req_id not in {r.req_id for r in requirements}:
            raise ValueError(f"unknown requirement {req_id!r}")
        if status not in VALID:
            raise ValueError(f"invalid status {status!r} for {req_id}")
    by_framework = {}
    by_function = {}
    gaps = []
    for r in requirements:
        status = results.get(r.req_id, "Not Met")
        score = {"Met": 1.0, "Partial": 0.5, "Not Met": 0.0}[status]
        for bucket in (by_framework, by_function):
            key = r.framework if bucket is by_framework else r.function
            got, total = bucket.get(key, (0.0, 0))
            bucket[key] = (got + score * r.weight, total + r.weight)
        if status != "Met":
            gaps.append({
                "req_id": r.req_id,
                "framework": r.framework,
                "function": r.function,
                "requirement": r.requirement,
                "status": status,
            })

    def coverage(bucket):
        return {k: round(got / total * 100, 1) if total else 0.0
                for k, (got, total) in sorted(bucket.items())}

    overall_got = sum(g for g, _ in by_framework.values())
    overall_total = sum(t for _, t in by_framework.values())
    return {
        "framework_coverage": coverage(by_framework),
        "function_coverage": coverage(by_function),
        "overall_coverage": round(overall_got / overall_total * 100, 1) if overall_total else 0.0,
        "gaps": gaps,
    }
