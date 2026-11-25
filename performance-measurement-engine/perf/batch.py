"""Single-pass batch computation over many funds and definitions.

The index-calculation workload is ~15,000 funds x ~150 measure
definitions. This module computes it in one pass: each fund's data is
read once, each requested measure is evaluated once per fund, and
results are cached under a key of (data snapshot hash, measure name,
measure version). A fund whose snapshot hash is already in the cache
— the same data seen before, or two funds with identical inputs — is
never recomputed. The cache key includes the measure version, so a
methodology change invalidates exactly the affected measures and
nothing else.
"""

from dataclasses import dataclass
from decimal import Decimal

from .conformance import MEASURE_VERSIONS, data_snapshot_hash
from .decimal_solver import solve_irr_decimal
from .decimal_measures import decimal_modified_dietz
from .pme import ks_pme, direct_alpha, long_nickels_pme


@dataclass(frozen=True)
class FundData:
    """One fund's calculation inputs, all Decimal.

    flows follow the fund's view: positive = contribution in,
    negative = distribution out. index_levels maps each flow day (and
    the end day) to the public-index level on that day.
    """
    fund_id: str
    flows: tuple  # ((Decimal day, Decimal amount), ...)
    index_levels: tuple  # ((Decimal day, Decimal level), ...)
    end_day: Decimal
    terminal_nav: Decimal
    start_value: Decimal
    end_value: Decimal
    start_day: Decimal = Decimal(0)

    def snapshot(self):
        """Data-snapshot hash pinning this fund's inputs."""
        return data_snapshot_hash({
            "flows": [[str(d), str(a)] for d, a in self.flows],
            "index_levels": [[str(d), str(v)] for d, v in self.index_levels],
            "end_day": str(self.end_day),
            "terminal_nav": str(self.terminal_nav),
            "start_value": str(self.start_value),
            "end_value": str(self.end_value),
            "start_day": str(self.start_day),
        })


def _investor_flows(fund):
    """Fund-view flows negated to the investor's view for IRR."""
    return [(day, -amount) for day, amount in fund.flows]


def _measure_functions():
    return {
        "irr_decimal": lambda f: solve_irr_decimal(_investor_flows(f))[0],
        "modified_dietz_decimal": lambda f: decimal_modified_dietz(
            f.start_value, f.end_value, f.flows,
            start_day=f.start_day, end_day=f.end_day),
        "ks_pme": lambda f: ks_pme(f.flows, dict(f.index_levels)),
        "direct_alpha": lambda f: direct_alpha(
            _investor_flows(f), dict(f.index_levels))[0],
        "long_nickels_pme": lambda f: long_nickels_pme(
            f.flows, dict(f.index_levels), f.end_day,
            terminal_nav=f.terminal_nav),
    }


def compute_batch(funds, definitions, cache=None):
    """Compute definitions for every fund in a single pass.

    funds: iterable of FundData. definitions: list of measure names
    (see MEASURE_VERSIONS). cache: optional dict shared across calls;
    keys are (snapshot hash, measure, version). Returns a dict with
    "results" ({fund_id: {measure: Decimal}}), "stats" (funds seen,
    computations run, cache hits), and "cache" (the cache dict used).
    """
    if cache is None:
        cache = {}
    functions = _measure_functions()
    unknown = [d for d in definitions if d not in functions]
    if unknown:
        raise ValueError("unknown measure definitions: %r" % (unknown,))
    results = {}
    stats = {"funds": 0, "computations": 0, "cache_hits": 0}
    for fund in funds:
        stats["funds"] += 1
        snapshot = fund.snapshot()
        fund_results = {}
        for name in definitions:
            key = (snapshot, name, MEASURE_VERSIONS[name])
            if key in cache:
                stats["cache_hits"] += 1
                fund_results[name] = cache[key]
            else:
                value = functions[name](fund)
                cache[key] = value
                stats["computations"] += 1
                fund_results[name] = value
        results[fund.fund_id] = fund_results
    return {"results": results, "stats": stats, "cache": cache}
