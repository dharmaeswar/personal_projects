"""Versioned conformance harness: golden vectors and run pinning.

Every measure the calculation library exposes is registered here with
a stable name and a semantic version. A measure's version changes only
when its methodology changes, so a stored result can always be traced
back to the exact code that produced it.

Reproducibility pinning: each run is pinned to
- a data snapshot hash (SHA-256 of the canonical fund inputs),
- the engine version,
- the measure versions used,
- an input hash (SHA-256 of the canonical request).

The conformance harness runs the golden vectors from the methodology
documents on every build, plus the invariant checks (date-shift,
netting, weight sums, monotonicity). ``run_conformance()`` returns a
report dict; it raises nothing on a failure, so a build script can
print the report and fail on ``report["failed"]``.
"""

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from .decimal_solver import money, solve_irr_decimal, decimal_npv
from .decimal_measures import decimal_modified_dietz, chained_index
from .pme import ks_pme, direct_alpha, long_nickels_pme

ENGINE_VERSION = "0.2.0"

MEASURE_VERSIONS = {
    "irr_decimal": "1.0.0",
    "modified_dietz_decimal": "1.0.0",
    "ks_pme": "1.0.0",
    "direct_alpha": "1.0.0",
    "long_nickels_pme": "1.0.0",
    "chained_index": "1.0.0",
}


def canonical_json(value):
    """Canonical JSON for hashing: sorted keys, Decimals as strings."""
    def convert(item):
        if isinstance(item, Decimal):
            return {"__decimal__": str(item)}
        if isinstance(item, dict):
            return {str(k): convert(v) for k, v in sorted(item.items())}
        if isinstance(item, (list, tuple)):
            return [convert(v) for v in item]
        return item
    return json.dumps(convert(value), sort_keys=True, separators=(",", ":"))


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def input_hash(request):
    """SHA-256 of the canonical form of a calculation request."""
    return sha256_hex(canonical_json(request))


def data_snapshot_hash(fund_inputs):
    """SHA-256 pin for a fund's data snapshot: flows, index levels,
    valuations and terminal NAV, in canonical form."""
    return sha256_hex(canonical_json(fund_inputs))


@dataclass(frozen=True)
class RunPin:
    """Everything needed to reproduce a run exactly."""
    data_snapshot: str
    engine_version: str = ENGINE_VERSION
    measure_versions: dict = field(default_factory=lambda: dict(MEASURE_VERSIONS))
    request_hash: str = ""

    def as_dict(self):
        return {
            "data_snapshot": self.data_snapshot,
            "engine_version": self.engine_version,
            "measure_versions": dict(self.measure_versions),
            "request_hash": self.request_hash,
        }


def pin_run(fund_inputs, request):
    """Build the RunPin for a calculation request over fund inputs."""
    return RunPin(
        data_snapshot=data_snapshot_hash(fund_inputs),
        request_hash=input_hash(request),
    )


# Golden vectors, hand-computed from the methodology documents.
# Each vector names a measure, its inputs, and the exact expected
# Decimal result. Tolerances are Decimal so a vector can demand an
# exact match (tolerance 0) where the methodology gives one.
GOLDEN_VECTORS = [
    {
        "name": "irr_decimal: -100 at t=0, +110 at t=1 is exactly 10%",
        "measure": "irr_decimal",
        "inputs": {"cash_flows": [["0", "-100"], ["1", "110"]]},
        "expected": "0.1",
        "tolerance": "0",
    },
    {
        "name": "irr_decimal: -1000, +100 at 0.5, +1100 at 1 is 21%",
        "measure": "irr_decimal",
        "inputs": {"cash_flows": [["0", "-1000"], ["0.5", "100"], ["1", "1100"]]},
        "expected": "0.21",
        "tolerance": "1e-15",
    },
    {
        "name": "modified_dietz_decimal: (130-100-20)/(100+20*0.5) = 10/110",
        "measure": "modified_dietz_decimal",
        "inputs": {"start_value": "100", "end_value": "130",
                   "flows": [["0.5", "20"]], "start_day": "0", "end_day": "1"},
        "expected": "0.09090909090909090909090909091",
        "tolerance": "1e-25",
    },
    {
        "name": "ks_pme: 100 in, 121 out, index 100->110 is 1.10",
        "measure": "ks_pme",
        "inputs": {"cash_flows": [["0", "100"], ["1", "-121"]],
                   "index_levels": [["0", "100"], ["1", "110"]]},
        "expected": "1.1",
        "tolerance": "0",
    },
    {
        "name": "direct_alpha: -100, +121, index 100->110 is 0.10",
        "measure": "direct_alpha",
        "inputs": {"cash_flows": [["0", "-100"], ["1", "121"]],
                   "index_levels": [["0", "100"], ["1", "110"]]},
        "expected": "0.1",
        "tolerance": "1e-15",
    },
    {
        "name": "long_nickels_pme: 100 in, 121 out, index to 121 at t=2 is 1.10",
        "measure": "long_nickels_pme",
        "inputs": {"cash_flows": [["0", "100"], ["1", "-121"]],
                   "index_levels": [["0", "100"], ["1", "110"], ["2", "121"]],
                   "end_day": "2"},
        "expected": "1.1",
        "tolerance": "0",
    },
    {
        "name": "chained_index: 10% then 10% from 100 is 121",
        "measure": "chained_index",
        "inputs": {"sub_period_returns": ["0.1", "0.1"]},
        "expected": "121",
        "tolerance": "0",
    },
]


def _run_vector(vector):
    """Run one golden vector. Returns (passed, actual, message)."""
    measure = vector["measure"]
    inputs = vector["inputs"]
    expected = Decimal(vector["expected"])
    tolerance = Decimal(vector["tolerance"])
    try:
        if measure == "irr_decimal":
            flows = [(Decimal(d), Decimal(a))
                     for d, a in inputs["cash_flows"]]
            actual, _ = solve_irr_decimal(flows)
        elif measure == "modified_dietz_decimal":
            flows = [(Decimal(d), Decimal(a)) for d, a in inputs["flows"]]
            actual = decimal_modified_dietz(
                inputs["start_value"], inputs["end_value"], flows,
                start_day=inputs["start_day"], end_day=inputs["end_day"])
        elif measure == "ks_pme":
            flows = [(Decimal(d), Decimal(a))
                     for d, a in inputs["cash_flows"]]
            levels = {Decimal(d): Decimal(v)
                      for d, v in inputs["index_levels"]}
            actual = ks_pme(flows, levels)
        elif measure == "direct_alpha":
            flows = [(Decimal(d), Decimal(a))
                     for d, a in inputs["cash_flows"]]
            levels = {Decimal(d): Decimal(v)
                      for d, v in inputs["index_levels"]}
            actual, _ = direct_alpha(flows, levels)
        elif measure == "long_nickels_pme":
            flows = [(Decimal(d), Decimal(a))
                     for d, a in inputs["cash_flows"]]
            levels = {Decimal(d): Decimal(v)
                      for d, v in inputs["index_levels"]}
            actual = long_nickels_pme(flows, levels, inputs["end_day"])
        elif measure == "chained_index":
            actual = chained_index(inputs["sub_period_returns"])[-1]
        else:
            return False, None, "unknown measure %r" % (measure,)
    except Exception as exc:  # noqa: BLE001 - harness reports, never raises
        return False, None, "raised %s: %s" % (type(exc).__name__, exc)
    if abs(actual - expected) <= tolerance:
        return True, actual, "actual %s matches expected %s" % (actual, expected)
    return False, actual, "actual %s != expected %s" % (actual, expected)


def check_invariants():
    """Invariant checks from the methodology: date-shift, netting,
    weight sums, monotonicity. Returns a list of (name, passed, message)."""
    checks = []

    # Date-shift: shifting every flow day by the same amount leaves
    # the IRR unchanged (only relative times matter). The IRR solver
    # requires the first flow at day 0, so the shifted case is solved
    # through the root solver directly on the shifted NPV.
    from .decimal_solver import solve_root_decimal
    base, _ = solve_irr_decimal(
        [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(110))])
    shifted_flows = [(Decimal(1), Decimal(-100)), (Decimal(2), Decimal(110))]
    shifted, _ = solve_root_decimal(
        lambda r: decimal_npv(shifted_flows, r), "-0.9999", "10")
    checks.append(("date-shift: IRR depends only on relative times",
                   base == shifted,
                   "base %s, shifted %s" % (base, shifted)))

    # Netting: two same-day flows equal their net in the IRR solve.
    split, _ = solve_irr_decimal(
        [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(60)),
         (Decimal(1), Decimal(50))])
    netted, _ = solve_irr_decimal(
        [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(110))])
    checks.append(("netting: same-day flows equal their net",
                   split == netted,
                   "split %s, netted %s" % (split, netted)))

    # Weight sums: discounted flow weights sum to exactly 1.
    from .pme import discounted_weights
    weights = discounted_weights(
        [(Decimal(0), Decimal(100)), (Decimal(1), Decimal(-121))],
        {Decimal(0): Decimal(100), Decimal(1): Decimal(110)})
    total = sum(w for _, w in weights)
    checks.append(("weight sums: discounted flow weights sum to 1",
                   total == Decimal(1),
                   "weight sum %s" % (total,)))

    # Monotonicity: a larger terminal distribution raises the IRR.
    small, _ = solve_irr_decimal(
        [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(105))])
    large, _ = solve_irr_decimal(
        [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(110))])
    checks.append(("monotonicity: larger distribution raises IRR",
                   small < large,
                   "small %s, large %s" % (small, large)))

    # Dietz netting: splitting a flow into same-day parts leaves
    # Modified Dietz unchanged.
    dietz_split = decimal_modified_dietz(
        "100", "130", [("0.5", "12"), ("0.5", "8")])
    dietz_net = decimal_modified_dietz("100", "130", [("0.5", "20")])
    checks.append(("netting: split same-day flow leaves Dietz unchanged",
                   dietz_split == dietz_net,
                   "split %s, netted %s" % (dietz_split, dietz_net)))
    return checks


def run_conformance():
    """Run every golden vector and invariant check. Returns a report
    dict with passed/failed lists and the engine + measure versions
    the run was pinned to."""
    report = {
        "engine_version": ENGINE_VERSION,
        "measure_versions": dict(MEASURE_VERSIONS),
        "passed": [],
        "failed": [],
    }
    for vector in GOLDEN_VECTORS:
        passed, actual, message = _run_vector(vector)
        entry = {"name": vector["name"], "measure": vector["measure"],
                 "message": message}
        (report["passed"] if passed else report["failed"]).append(entry)
    for name, passed, message in check_invariants():
        entry = {"name": name, "measure": "invariant", "message": message}
        (report["passed"] if passed else report["failed"]).append(entry)
    report["summary"] = "%d passed, %d failed" % (
        len(report["passed"]), len(report["failed"]))
    return report
