"""MCP-style tool registry.

Agents never touch data or code directly; they call named tools through this
registry, the way an MCP client calls tools on a server. Each tool declares
its name, a description, and its required parameters. Unknown tools and
missing parameters raise instead of failing silently, and every call is
logged so a trajectory can be replayed and audited.
"""

import math
import random
import statistics

from .corpus import get_document

# Seeded daily-return series (synthetic, fixed seed) used by the compute
# tools. Generated deterministically from a fixed random seed, with moments
# chosen to match the seeded dataset documents (momentum: 6.2% return,
# 11.4% vol; carry: 4.8% return, 9.1% vol). Values are invented for this
# demo, not real market data.
def _seeded_series(mu_daily, sigma_daily, n=252, seed=7):
    """Deterministic 252-point series with exact target sample moments.

    Raw Gaussian draws from a fixed seed are shifted and scaled so the
    sample mean and sample standard deviation equal the targets exactly.
    Computed statistics therefore corroborate the seeded dataset figures
    instead of drifting away from them by sampling noise.
    """
    rng = random.Random(seed)
    raw = [rng.gauss(0.0, 1.0) for _ in range(n)]
    mean = statistics.fmean(raw)
    std = statistics.stdev(raw)
    return [mu_daily + (x - mean) * (sigma_daily / std) for x in raw]


SEEDED_SERIES = {
    "momentum": _seeded_series(0.062 / 252, 0.114 / math.sqrt(252), seed=7),
    "carry": _seeded_series(0.048 / 252, 0.091 / math.sqrt(252), seed=11),
}

# Ground-truth figures from the seeded dataset documents, used by the
# validator to re-check numbers quoted in a draft answer.
GROUND_TRUTH = {
    "momentum annualised return": 6.2,
    "momentum volatility": 11.4,
    "momentum sharpe": 0.54,
    "carry annualised return": 4.8,
    "carry volatility": 9.1,
    "carry sharpe": 0.53,
    "volatility target": 10.0,
    "realised volatility": 10.3,
    "leverage cap": 2.0,
    "mean reversion sharpe": 0.28,
}


class ToolError(Exception):
    """Raised for unknown tools, missing parameters, or bad arguments."""


class ToolRegistry:
    """Named tools with declared parameters, handlers, and a call log."""

    def __init__(self, knowledge_layer):
        self.knowledge = knowledge_layer
        self.call_log = []
        self._tools = {
            "search_knowledge": {
                "description": "Search the knowledge layer over research notes, code, and datasets.",
                "params": ["query"],
                "handler": self._search_knowledge,
            },
            "read_code": {
                "description": "Return a research-code document by id.",
                "params": ["doc_id"],
                "handler": self._read_code,
            },
            "compute_statistic": {
                "description": "Compute mean, volatility, or Sharpe ratio of a seeded return series.",
                "params": ["series", "statistic"],
                "handler": self._compute_statistic,
            },
            "validate_number": {
                "description": "Re-check a quoted figure against the seeded dataset ground truth.",
                "params": ["label", "value"],
                "handler": self._validate_number,
            },
        }

    def list_tools(self):
        """Names and descriptions of every registered tool."""
        return [
            {"name": name, "description": spec["description"]}
            for name, spec in self._tools.items()
        ]

    def call(self, name, args):
        """Call a tool by name with an args dict; logs the call."""
        if name not in self._tools:
            raise ToolError(f"unknown tool: {name}")
        missing = [p for p in self._tools[name]["params"] if p not in args]
        if missing:
            raise ToolError(f"tool {name} missing parameters: {', '.join(missing)}")
        result = self._tools[name]["handler"](args)
        self.call_log.append({"tool": name, "args": dict(args), "result": result})
        return result

    def _search_knowledge(self, args):
        return self.knowledge.search(
            args["query"], kind=args.get("kind"), top_k=args.get("top_k", 3)
        )

    def _read_code(self, args):
        doc = get_document(args["doc_id"])
        if doc is None or doc["kind"] != "code":
            raise ToolError(f"no code document with id: {args['doc_id']}")
        return {"doc_id": doc["id"], "title": doc["title"], "text": doc["text"]}

    def _compute_statistic(self, args):
        series = SEEDED_SERIES.get(args["series"])
        if series is None:
            raise ToolError(f"unknown series: {args['series']}")
        statistic = args["statistic"]
        if statistic == "mean":
            return {"series": args["series"], "statistic": "mean",
                    "value": round(statistics.fmean(series), 6)}
        if statistic == "volatility":
            daily = statistics.stdev(series)
            return {"series": args["series"], "statistic": "volatility",
                    "value": round(daily * math.sqrt(252), 4)}
        if statistic == "sharpe":
            mean = statistics.fmean(series)
            daily = statistics.stdev(series)
            annual = mean * 252 / (daily * math.sqrt(252))
            return {"series": args["series"], "statistic": "sharpe",
                    "value": round(annual, 2)}
        raise ToolError(f"unknown statistic: {statistic}")

    def _validate_number(self, args):
        label = args["label"].lower()
        truth = GROUND_TRUTH.get(label)
        if truth is None:
            return {"label": args["label"], "checked": False,
                    "reason": "no ground truth for this label"}
        value = float(args["value"])
        ok = abs(value - truth) <= 0.05
        return {"label": args["label"], "checked": True, "expected": truth,
                "value": value, "match": ok}
