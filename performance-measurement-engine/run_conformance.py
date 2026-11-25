"""Demo: conformance harness and single-pass batch computation.

Runs the golden vectors and invariant checks, pins one run to its
data snapshot, then computes five measures for 300 synthetic funds
in a single pass and re-runs the same batch from the cache.
"""

from decimal import Decimal

from perf import run_conformance, pin_run, FundData, compute_batch

D = Decimal


def main():
    report = run_conformance()
    print("Conformance (%s): %s" % (report["engine_version"], report["summary"]))
    for entry in report["failed"]:
        print("  FAILED: %s — %s" % (entry["name"], entry["message"]))

    fund_inputs = {"flows": [["0", "100"], ["1", "-121"]],
                   "index_levels": [["0", "100"], ["1", "110"]]}
    request = {"fund": "DEMO-1", "measures": ["irr_decimal", "ks_pme"]}
    pin = pin_run(fund_inputs, request)
    print("Run pin: snapshot %s..., request %s..."
          % (pin.data_snapshot[:12], pin.request_hash[:12]))
    print("Measure versions: %s" % (pin.measure_versions,))

    definitions = ["irr_decimal", "modified_dietz_decimal", "ks_pme",
                   "direct_alpha", "long_nickels_pme"]
    funds = []
    for i in range(300):
        funds.append(FundData(
            fund_id="F%03d" % i,
            flows=((D(0), D(100 + i)), (D(1), D(-(121 + i)))),
            index_levels=((D(0), D(100)), (D(1), D(110))),
            end_day=D(1), terminal_nav=D(0),
            start_value=D(100), end_value=D(110)))
    cache = {}
    out = compute_batch(funds, definitions, cache=cache)
    print("Batch: %d funds, %d computations, %d cache hits"
          % (out["stats"]["funds"], out["stats"]["computations"],
             out["stats"]["cache_hits"]))
    print("F000 IRR %.4f%%, KS-PME %.4f, Direct Alpha %.4f%%"
          % (out["results"]["F000"]["irr_decimal"] * 100,
             out["results"]["F000"]["ks_pme"],
             out["results"]["F000"]["direct_alpha"] * 100))
    again = compute_batch(funds, definitions, cache=cache)
    print("Re-run from cache: %d computations, %d cache hits"
          % (again["stats"]["computations"], again["stats"]["cache_hits"]))


if __name__ == "__main__":
    main()
