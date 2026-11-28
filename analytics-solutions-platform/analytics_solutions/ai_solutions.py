"""AI solutions layer: agentic, grounded answers for Client Services stakeholders.

This is the "solution delivery" half of the platform: a stakeholder asks a
question in plain words ("which client segment drove volume last month, and
why?") and an agentic runner plans tool calls, executes them against the
governed registry and datasets, and answers — but only with numbers that
trace back to a computed metric or dataset. A number with no source is
rejected instead of reported, so the solution can never hallucinate a KPI.

Tools available to the planner:
  - ``get_metric`` — compute a registered, governed metric (metrics.py).
  - ``find_dataset`` — locate the governed dataset that answers the
    question (discovery.py); an explicit "no match" instead of guessing.
  - ``run_enrichment`` — build enriched client records from new sources
    (this module): joins, windowed 30-day aggregates, anomaly flags.
  - ``driver_analysis`` — OLS driver analysis of a target on features,
    implemented from scratch in the standard library (this module).

Everything is deterministic and reproducible: the solution manifest records
the run id, seed, question, plan, every tool call and result, and a SHA-256
hash of the canonical inputs, so the same inputs always reproduce the same
answer. All data is synthetic and seeded in code.

The enrichment transforms are pure row-wise functions, so the same logic
ports directly to PySpark DataFrame operations at scale; the local run uses
the standard library only, matching the rest of this project.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date

from .discovery import answer_question as discover_dataset
from .metrics import compute_metrics


class AISolutionsError(ValueError):
    pass


class GroundingError(AISolutionsError):
    pass


class DriverError(AISolutionsError):
    pass


# ---------------------------------------------------------------------------
# Data enrichment pipeline (new sources -> enriched client records)
# ---------------------------------------------------------------------------

def _to_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        parts = str(value).split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError, TypeError):
        return None


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zscore(value: float, mean: float, stdev: float) -> float:
    if stdev <= 0:
        return 0.0
    return (value - mean) / stdev


def enrich_client_records(clients: list[dict], transactions: list[dict],
                          activities: list[dict], as_of: date,
                          window_days: int = 30) -> tuple[list[dict], list[dict]]:
    """Join clients with transaction and activity feeds into enriched records.

    For each client: 30-day transaction count/volume/average ticket, lifetime
    volume, recency in days, 30-day activity count, and an anomaly flag when
    the client's 30-day volume is more than 2 standard deviations above its
    segment mean (segments with fewer than 3 clients are not scored).

    Bad rows are quarantined with a named reason and never silently dropped:
    negative or missing amount, duplicate transaction id, unknown client id,
    or an unparseable date. Transactions outside the window still count
    toward lifetime volume.
    """
    if window_days <= 0:
        raise AISolutionsError("window_days must be positive")
    known = {str(c["client_id"]) for c in clients if c.get("client_id")}
    enriched: list[dict] = []
    quarantined: list[dict] = []
    seen_txn: set[str] = set()
    txns_by_client: dict[str, list[dict]] = {cid: [] for cid in known}
    acts_by_client: dict[str, list[dict]] = {cid: [] for cid in known}

    for txn in transactions:
        txn_id = str(txn.get("txn_id", "")).strip()
        cid = str(txn.get("client_id", "")).strip()
        amount = _to_float(txn.get("amount"))
        txn_date = _to_date(txn.get("txn_date"))
        reason = None
        if not txn_id or txn_id in seen_txn:
            reason = "duplicate or missing txn_id"
        elif cid not in known:
            reason = "unknown client_id"
        elif amount is None or amount < 0:
            reason = "negative or missing amount"
        elif txn_date is None:
            reason = "unparseable txn_date"
        if reason is not None:
            quarantined.append({**txn, "quarantine_reason": reason})
            continue
        seen_txn.add(txn_id)
        txns_by_client[cid].append({"amount": amount, "txn_date": txn_date})

    for act in activities:
        cid = str(act.get("client_id", "")).strip()
        act_date = _to_date(act.get("activity_date"))
        if cid not in known:
            quarantined.append({**act, "quarantine_reason": "unknown client_id"})
            continue
        if act_date is None:
            quarantined.append({**act, "quarantine_reason": "unparseable activity_date"})
            continue
        acts_by_client[cid].append({"activity_date": act_date})

    for client in clients:
        cid = str(client["client_id"])
        txns = txns_by_client[cid]
        acts = acts_by_client[cid]
        window = [t for t in txns if 0 <= (as_of - t["txn_date"]).days < window_days]
        recent_acts = [a for a in acts if 0 <= (as_of - a["activity_date"]).days < window_days]
        volume_30d = round(sum(t["amount"] for t in window), 2)
        count_30d = len(window)
        last_txn = max((t["txn_date"] for t in txns), default=None)
        enriched.append({
            "client_id": cid,
            "segment": client.get("segment"),
            "channel": client.get("channel"),
            "txn_count_30d": count_30d,
            "txn_volume_30d": volume_30d,
            "avg_ticket_30d": round(volume_30d / count_30d, 2) if count_30d else 0.0,
            "lifetime_volume": round(sum(t["amount"] for t in txns), 2),
            "txn_count_total": len(txns),
            "recency_days": (as_of - last_txn).days if last_txn else None,
            "activity_count_30d": len(recent_acts),
            "anomaly": False,
        })

    segments: dict[str, list[dict]] = {}
    for row in enriched:
        segments.setdefault(str(row["segment"]), []).append(row)
    for rows in segments.values():
        if len(rows) < 3:
            continue
        volumes = [r["txn_volume_30d"] for r in rows]
        mean = sum(volumes) / len(volumes)
        var = sum((v - mean) ** 2 for v in volumes) / len(volumes)
        stdev = math.sqrt(var)
        for row in rows:
            if _zscore(row["txn_volume_30d"], mean, stdev) > 2.0:
                row["anomaly"] = True
    return enriched, quarantined


# ---------------------------------------------------------------------------
# Driver analysis: OLS from scratch (standard library only)
# ---------------------------------------------------------------------------

def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a small dense linear system by Gaussian elimination."""
    n = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise DriverError("singular design matrix: features are collinear")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for r in range(col + 1, n):
            factor = aug[r][col] / aug[col][col]
            for c in range(col, n + 1):
                aug[r][c] -= factor * aug[col][c]
    out = [0.0] * n
    for i in range(n - 1, -1, -1):
        out[i] = (aug[i][n] - sum(aug[i][j] * out[j] for j in range(i + 1, n))) / aug[i][i]
    return out


def driver_analysis(rows: list[dict], target: str,
                    features: list[str]) -> dict:
    """Regress ``target`` on ``features`` and name the strongest driver.

    Returns coefficients, intercept, R-squared, row count, and a
    plain-language readout. Rows missing the target or any feature are
    skipped and counted; fewer than (features + 2) usable rows raises.
    """
    usable = [r for r in rows
              if r.get(target) is not None
              and all(r.get(f) is not None for f in features)]
    skipped = len(rows) - len(usable)
    if len(usable) < len(features) + 2:
        raise DriverError(
            f"need at least {len(features) + 2} usable rows, got {len(usable)}")
    y = [float(r[target]) for r in usable]
    x = [[1.0] + [float(r[f]) for f in features] for r in usable]
    k = len(features) + 1
    xtx = [[sum(row[i] * row[j] for row in x) for j in range(k)] for i in range(k)]
    xty = [sum(row[i] * yv for row, yv in zip(x, y)) for i in range(k)]
    beta = _solve_linear(xtx, xty)
    y_mean = sum(y) / len(y)
    ss_tot = sum((v - y_mean) ** 2 for v in y)
    preds = [sum(b * v for b, v in zip(beta, row)) for row in x]
    ss_res = sum((v - p) ** 2 for v, p in zip(y, preds))
    r2 = round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0
    coeffs = {f: round(beta[i + 1], 4) for i, f in enumerate(features)}
    strongest = max(features, key=lambda f: abs(coeffs[f])) if features else None
    direction = "increases" if strongest and coeffs[strongest] > 0 else "decreases"
    readout = (f"{strongest} is the strongest driver of {target}: a one-unit rise "
               f"{direction} {target} by {abs(coeffs[strongest])} "
               f"(R-squared {r2}, n={len(usable)})."
               if strongest else "no features supplied.")
    return {"target": target, "features": list(features),
            "coefficients": coeffs, "intercept": round(beta[0], 4),
            "r_squared": r2, "n": len(usable), "skipped": skipped,
            "strongest_driver": strongest, "readout": readout}


# ---------------------------------------------------------------------------
# Grounding: every number in an answer must trace to computed evidence
# ---------------------------------------------------------------------------

def validate_grounding(answer: str, evidence: dict[str, float | int]) -> list[str]:
    """Return the numbers in ``answer`` that have no matching evidence value.

    A number is grounded when it appears (rounded to 2 decimals) among the
    evidence values. Dates and counts written as plain integers are checked
    the same way. An empty list means the answer is fully grounded.
    """
    found = set()
    for token in re.findall(r"-?\d[\d,]*\.?\d*", answer):
        try:
            found.add(round(float(token.replace(",", "")), 2))
        except ValueError:
            continue
    grounded = {round(float(v), 2) for v in evidence.values()}
    return [str(v) for v in sorted(found) if v not in grounded]


# ---------------------------------------------------------------------------
# Agentic solution runner: plan -> tools -> grounded answer -> manifest
# ---------------------------------------------------------------------------

_METRIC_WORDS = ("active", "premium", "volume", "count", "average", "share", "activity")
_DRIVER_WORDS = ("why", "driver", "drives", "drive", "cause", "explain")


def plan_solution(question: str) -> list[dict]:
    """Plan tool calls for a stakeholder question from its keywords."""
    q = question.lower()
    plan: list[dict] = []
    if any(w in q for w in _METRIC_WORDS):
        plan.append({"tool": "get_metric", "args": {}})
    plan.append({"tool": "find_dataset", "args": {"question": question}})
    if "enrich" in q or "new source" in q or "segment" in q or "client" in q:
        plan.append({"tool": "run_enrichment", "args": {}})
    if any(w in q for w in _DRIVER_WORDS):
        if not any(step["tool"] == "run_enrichment" for step in plan):
            plan.append({"tool": "run_enrichment", "args": {}})
        plan.append({"tool": "driver_analysis",
                     "args": {"target": "txn_volume_30d",
                              "features": ["txn_count_30d", "activity_count_30d"]}})
    return plan


def run_solution(question: str, *, registry, facts: list[dict],
                 catalog: list[dict], clients: list[dict],
                 transactions: list[dict], activities: list[dict],
                 as_of: date, run_id: str, seed: int = 0) -> dict:
    """Execute the plan for ``question`` and return a grounded solution.

    The answer only reports numbers computed by the tools; any number that
    cannot be traced to evidence raises GroundingError instead of shipping.
    The manifest (run id, seed, plan, tool calls, input hash) makes the
    solution reproducible from the same inputs.
    """
    plan = plan_solution(question)
    if not plan:
        raise AISolutionsError("no tool plan for this question")
    evidence: dict[str, float | int] = {"enriched_clients": 0, "quarantined_rows": 0}
    tool_calls: list[dict] = []
    enriched: list[dict] = []
    driver: dict | None = None

    for step in plan:
        tool = step["tool"]
        if tool == "get_metric":
            result = compute_metrics(registry, facts)
            evidence.update(result)
            tool_calls.append({"tool": tool, "result": result})
        elif tool == "find_dataset":
            result = discover_dataset(catalog, question)
            tool_calls.append({"tool": tool, "result": result})
        elif tool == "run_enrichment":
            enriched, quarantined = enrich_client_records(
                clients, transactions, activities, as_of)
            top = max(enriched, key=lambda r: r["txn_volume_30d"]) if enriched else None
            if top is not None:
                evidence["top_segment_volume_30d"] = top["txn_volume_30d"]
                evidence["top_segment_txn_count_30d"] = top["txn_count_30d"]
            evidence["enriched_clients"] = len(enriched)
            evidence["quarantined_rows"] = len(quarantined)
            tool_calls.append({"tool": tool, "result": {
                "enriched": len(enriched), "quarantined": len(quarantined),
                "anomalies": sum(1 for r in enriched if r["anomaly"]),
                "top_client": top["client_id"] if top else None}})
        elif tool == "driver_analysis":
            source = enriched or []
            driver = driver_analysis(source, step["args"]["target"],
                                     step["args"]["features"])
            evidence["driver_r_squared"] = driver["r_squared"]
            evidence["window_days"] = 30
            for feat, coef in driver["coefficients"].items():
                evidence[f"driver_coef_{feat}"] = coef
            evidence["driver_n"] = driver["n"]
            tool_calls.append({"tool": tool, "result": driver})

    evidence["window_days"] = 30
    segments: dict[str, float] = {}
    for row in enriched:
        segments[str(row["segment"])] = round(
            segments.get(str(row["segment"]), 0.0) + row["txn_volume_30d"], 2)
    if segments:
        top_segment = max(segments, key=lambda s: segments[s])
        evidence["top_segment_volume"] = segments[top_segment]
        answer = (f"{top_segment} leads 30-day volume at "
                  f"{segments[top_segment]} across {len(enriched)} enriched "
                  f"clients. {driver['readout'] if driver else ''}").strip()
    else:
        top_segment = None
        answer = (f"No enriched client records for this question; "
                  f"{len(enriched)} clients processed.")
    ungrounded = validate_grounding(answer, evidence)
    if ungrounded:
        raise GroundingError(f"answer cites ungrounded numbers: {ungrounded}")
    inputs = {"question": question, "seed": seed,
              "clients": clients, "transactions": transactions,
              "activities": activities, "as_of": str(as_of)}
    input_hash = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()
    return {"run_id": run_id, "question": question, "plan": plan,
            "tool_calls": tool_calls, "answer": answer,
            "top_segment": top_segment, "segment_volumes": segments,
            "evidence": evidence, "input_hash": input_hash}
