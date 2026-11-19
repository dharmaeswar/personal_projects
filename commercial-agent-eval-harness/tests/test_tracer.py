from agent_eval.tracer import Tracer


def test_record_adds_call_with_model_latency_and_cost():
    tracer = Tracer()
    call = tracer.record("lookup_invoice", {"invoice_id": "INV-1001"}, "ok")
    assert call.latency_ms == 45
    assert call.cost_usd == 120 / 1000 * 0.003
    assert tracer.total_latency_ms() == 45
    assert tracer.total_cost_usd() == round(120 / 1000 * 0.003, 6)


def test_totals_sum_across_calls():
    tracer = Tracer()
    tracer.record("lookup_invoice", {}, "ok")
    tracer.record("search_kb", {}, "ok")
    assert tracer.total_latency_ms() == 45 + 120
    assert tracer.tool_names() == ["lookup_invoice", "search_kb"]


def test_error_calls_are_counted():
    tracer = Tracer()
    tracer.record("lookup_invoice", {}, "ok")
    tracer.record("lookup_po", {}, "error", error="purchase order not found: PO-1")
    assert len(tracer.errors()) == 1
    assert tracer.errors()[0].error == "purchase order not found: PO-1"


def test_empty_tracer_totals_zero():
    tracer = Tracer()
    assert tracer.total_latency_ms() == 0
    assert tracer.total_cost_usd() == 0
    assert tracer.errors() == []


def test_to_dict_round_trips():
    tracer = Tracer()
    tracer.record("approve_invoice", {"invoice_id": "INV-1001"}, "ok")
    data = tracer.to_dict()
    assert data["total_latency_ms"] == 60
    assert data["error_count"] == 0
    assert data["calls"][0]["tool"] == "approve_invoice"
