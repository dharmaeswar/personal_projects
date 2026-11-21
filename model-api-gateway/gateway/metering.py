"""Usage metering and billing.

Every served request records prompt/completion tokens and latency. Usage
aggregates per key per day; billing prices tokens per model into invoice
lines. Prices are demo values in USD per 1,000 tokens.
"""

import threading
from collections import defaultdict

# Demo price list: model -> (price per 1K prompt tokens, per 1K completion tokens).
PRICES_PER_1K = {
    "llama-4-scout": (0.00035, 0.00140),
    "qwen3-32b": (0.00020, 0.00080),
    "deepseek-r1-distill": (0.00010, 0.00040),
}


class UsageRecord:
    def __init__(self, key_id, model, day, prompt_tokens, completion_tokens, latency_ms):
        self.key_id = key_id
        self.model = model
        self.day = day  # "YYYY-MM-DD"
        self.prompt_tokens = int(prompt_tokens)
        self.completion_tokens = int(completion_tokens)
        self.latency_ms = float(latency_ms)


class Meter:
    """Thread-safe usage log with per-key, per-day aggregation."""

    def __init__(self):
        self._records = []
        self._lock = threading.Lock()

    def record(self, usage):
        with self._lock:
            self._records.append(usage)

    def aggregate(self, key_id, day=None):
        """Return {model: {requests, prompt_tokens, completion_tokens, avg_latency_ms}}."""
        totals = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0,
                                      "completion_tokens": 0, "latency_sum": 0.0})
        with self._lock:
            records = [r for r in self._records
                       if r.key_id == key_id and (day is None or r.day == day)]
        for record in records:
            bucket = totals[record.model]
            bucket["requests"] += 1
            bucket["prompt_tokens"] += record.prompt_tokens
            bucket["completion_tokens"] += record.completion_tokens
            bucket["latency_sum"] += record.latency_ms
        out = {}
        for model, bucket in totals.items():
            out[model] = {
                "requests": bucket["requests"],
                "prompt_tokens": bucket["prompt_tokens"],
                "completion_tokens": bucket["completion_tokens"],
                "avg_latency_ms": (bucket["latency_sum"] / bucket["requests"]
                                   if bucket["requests"] else 0.0),
            }
        return out

    def total_requests(self):
        with self._lock:
            return len(self._records)


def price_for(model, prompt_tokens, completion_tokens):
    """USD cost of one request. Unknown models bill at zero (flagged, not charged)."""
    prices = PRICES_PER_1K.get(model)
    if prices is None:
        return 0.0
    prompt_price, completion_price = prices
    return (prompt_tokens / 1000.0) * prompt_price + \
           (completion_tokens / 1000.0) * completion_price


def build_invoice(key_id, usage_by_model):
    """Turn aggregated usage into invoice lines plus a total.

    usage_by_model is the output of Meter.aggregate for one key.
    """
    lines = []
    total = 0.0
    for model in sorted(usage_by_model):
        bucket = usage_by_model[model]
        amount = price_for(model, bucket["prompt_tokens"], bucket["completion_tokens"])
        total += amount
        lines.append({
            "key_id": key_id,
            "model": model,
            "requests": bucket["requests"],
            "prompt_tokens": bucket["prompt_tokens"],
            "completion_tokens": bucket["completion_tokens"],
            "amount_usd": round(amount, 6),
        })
    return {"key_id": key_id, "lines": lines, "total_usd": round(total, 6)}
