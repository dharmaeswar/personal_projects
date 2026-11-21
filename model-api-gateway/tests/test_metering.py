from gateway.metering import Meter, UsageRecord, build_invoice, price_for


def _meter():
    meter = Meter()
    meter.record(UsageRecord("k1", "llama-4-scout", "2026-11-21", 1000, 500, 120.0))
    meter.record(UsageRecord("k1", "llama-4-scout", "2026-11-21", 2000, 250, 140.0))
    meter.record(UsageRecord("k1", "qwen3-32b", "2026-11-21", 500, 100, 90.0))
    meter.record(UsageRecord("k2", "llama-4-scout", "2026-11-21", 100, 100, 100.0))
    return meter


def test_aggregate_groups_by_model_and_key():
    usage = _meter().aggregate("k1")
    assert usage["llama-4-scout"]["requests"] == 2
    assert usage["llama-4-scout"]["prompt_tokens"] == 3000
    assert usage["llama-4-scout"]["completion_tokens"] == 750
    assert usage["llama-4-scout"]["avg_latency_ms"] == 130.0
    assert usage["qwen3-32b"]["requests"] == 1
    assert "llama-4-scout" in _meter().aggregate("k2")


def test_aggregate_filters_by_day():
    assert _meter().aggregate("k1", day="2026-11-20") == {}


def test_price_for_uses_per_model_rates():
    # llama-4-scout: $0.00035/1K prompt, $0.00140/1K completion
    assert price_for("llama-4-scout", 1000, 1000) == 0.00175
    assert price_for("unknown-model", 1000, 1000) == 0.0


def test_invoice_totals_match_line_amounts():
    usage = _meter().aggregate("k1")
    invoice = build_invoice("k1", usage)
    assert invoice["key_id"] == "k1"
    assert len(invoice["lines"]) == 2
    assert invoice["total_usd"] == round(sum(l["amount_usd"] for l in invoice["lines"]), 6)
    assert invoice["total_usd"] > 0
