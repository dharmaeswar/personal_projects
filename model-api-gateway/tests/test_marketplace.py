"""Tests for the marketplace partner-intelligence module.

Covers partner dataset registration and schema-validated ingestion,
the governed semantic layer (metric definition + query with lineage),
the model-serving evaluation foundation (pass/fail gates), the
agent-evaluation foundation (expected-content cases with traces),
and the HTTP endpoints that expose them (including auth checks).
"""

from gateway.api import Gateway, make_handler
from gateway.serving import ModelVersion

KEY = "sk-test-1"
DATASET = {"dataset_id": "partner-sales",
           "name": "Partner Sales",
           "owner_partner": "demo-partner",
           "columns": [{"name": "partner", "type": "string"},
                       {"name": "region", "type": "string"},
                       {"name": "revenue", "type": "number"},
                       {"name": "active", "type": "boolean"}]}
ROWS = [{"partner": "acme", "region": "us", "revenue": 100, "active": True},
        {"partner": "acme", "region": "eu", "revenue": 250, "active": True},
        {"partner": "globex", "region": "us", "revenue": 50, "active": False}]
MODEL = {"name": "churn-risk", "version": "1.2.0",
         "framework": "scikit-learn",
         "features": [{"name": "tenure_months", "type": "number",
                       "required": True, "minimum": 0, "maximum": 600},
                      {"name": "monthly_spend", "type": "number",
                       "required": True, "minimum": 0, "maximum": 100000},
                      {"name": "support_tickets", "type": "number",
                       "required": True, "minimum": 0, "maximum": 100},
                      {"name": "is_enterprise", "type": "boolean",
                       "required": False}],
         "target": "churn_probability"}


def make_gateway():
    gateway = Gateway()
    gateway.keys.add_seeded(KEY, "test", "pro",
                            ("models:invoke", "usage:read", "billing:read"))
    return gateway


def seeded_gateway():
    """Gateway with one dataset ingested and one metric defined."""
    gateway = make_gateway()
    assert gateway.register_dataset(KEY, DATASET)[0] == 201
    status, result = gateway.ingest_dataset(KEY, "partner-sales", ROWS)
    assert status == 200
    assert result["accepted"] == 3
    assert result["rejected"] == 0
    status, metric = gateway.define_metric(
        KEY, {"name": "total_revenue", "dataset_id": "partner-sales",
              "column": "revenue", "aggregation": "sum"})
    assert status == 201
    return gateway


# ---- Ingestion ----------------------------------------------------------

def test_register_and_ingest_round_trip():
    gateway = make_gateway()
    status, created = gateway.register_dataset(KEY, DATASET)
    assert status == 201
    assert created["row_count"] == 0
    status, result = gateway.ingest_dataset(KEY, "partner-sales", ROWS)
    assert status == 200
    assert result["accepted"] == 3
    assert result["row_count"] == 3


def test_register_duplicate_dataset_returns_400():
    gateway = make_gateway()
    assert gateway.register_dataset(KEY, DATASET)[0] == 201
    status, payload = gateway.register_dataset(KEY, DATASET)
    assert status == 400
    assert payload["error"] == "invalid_dataset_spec"


def test_ingest_rejects_bad_rows_and_keeps_good_ones():
    gateway = make_gateway()
    gateway.register_dataset(KEY, DATASET)
    bad = [{"partner": "acme", "region": "us", "revenue": "lots", "active": True},
           {"partner": "acme", "region": "us", "active": True},
           {"partner": "acme", "region": "us", "revenue": 10,
            "active": True, "surprise": 1}]
    status, result = gateway.ingest_dataset(KEY, "partner-sales", bad)
    assert status == 200
    assert result["accepted"] == 0
    assert result["rejected"] == 3
    assert len(result["errors"]) == 3
    assert result["row_count"] == 0


def test_ingest_unknown_dataset_returns_404():
    gateway = make_gateway()
    status, payload = gateway.ingest_dataset(KEY, "nope", ROWS)
    assert status == 404
    assert payload["error"] == "unknown_dataset"


# ---- Governed semantic layer -------------------------------------------

def test_semantic_query_sum_and_filter_with_lineage():
    gateway = seeded_gateway()
    status, answer = gateway.query_metric(KEY, "total_revenue")
    assert status == 200
    assert answer["value"] == 400
    assert answer["rows_matched"] == 3
    assert answer["lineage"]["dataset_id"] == "partner-sales"
    assert answer["lineage"]["column"] == "revenue"
    status, filtered = gateway.query_metric(
        KEY, "total_revenue", {"region": "us"})
    assert status == 200
    assert filtered["value"] == 150
    assert filtered["rows_matched"] == 2


def test_semantic_avg_and_count():
    gateway = seeded_gateway()
    gateway.define_metric(KEY, {"name": "avg_revenue",
                                "dataset_id": "partner-sales",
                                "column": "revenue", "aggregation": "avg"})
    gateway.define_metric(KEY, {"name": "partner_rows",
                                "dataset_id": "partner-sales",
                                "column": "*", "aggregation": "count"})
    _, avg = gateway.query_metric(KEY, "avg_revenue")
    assert abs(avg["value"] - 400 / 3) < 1e-9
    _, count = gateway.query_metric(KEY, "partner_rows", {"active": True})
    assert count["value"] == 2


def test_define_metric_unknown_dataset_or_column_returns_400():
    gateway = make_gateway()
    status, _ = gateway.define_metric(
        KEY, {"name": "m", "dataset_id": "nope",
              "column": "revenue", "aggregation": "sum"})
    assert status == 400
    gateway.register_dataset(KEY, DATASET)
    status, _ = gateway.define_metric(
        KEY, {"name": "m", "dataset_id": "partner-sales",
              "column": "nope", "aggregation": "sum"})
    assert status == 400


def test_query_unknown_metric_returns_404():
    gateway = make_gateway()
    status, payload = gateway.query_metric(KEY, "nope")
    assert status == 404


def test_marketplace_endpoints_require_auth():
    gateway = seeded_gateway()
    assert gateway.register_dataset("bad-key", DATASET)[0] == 401
    assert gateway.ingest_dataset("bad-key", "partner-sales", ROWS)[0] == 401
    assert gateway.query_metric("bad-key", "total_revenue")[0] == 401


# ---- Model-serving evaluation -------------------------------------------

def _serving_gateway():
    gateway = make_gateway()
    assert gateway.register_model(KEY, MODEL)[0] == 201
    return gateway


def test_serving_eval_gate_passes_and_fetches_by_id():
    gateway = _serving_gateway()
    # churn-risk demo score for a long-tenure, low-spend customer is low.
    cases = [{"features": {"tenure_months": 120, "monthly_spend": 100,
                           "support_tickets": 0, "is_enterprise": False},
              "expected_min": 0.0, "expected_max": 0.6},
             {"features": {"tenure_months": 1, "monthly_spend": 900,
                           "support_tickets": 9, "is_enterprise": False},
              "expected_min": 0.0, "expected_max": 0.9}]
    status, run = gateway.run_serving_eval(
        KEY, {"model": "churn-risk", "cases": cases, "min_pass_rate": 0.5})
    assert status == 200
    assert run["cases_run"] == 2
    assert run["pass_rate"] == 1.0
    assert run["gate_passed"] is True
    status, fetched = gateway.get_serving_eval(KEY, run["run_id"])
    assert status == 200
    assert fetched["run_id"] == run["run_id"]
    assert fetched["gate_passed"] is True


def test_serving_eval_gate_fails_when_cases_miss_range():
    gateway = _serving_gateway()
    cases = [{"features": {"tenure_months": 120, "monthly_spend": 100,
                           "support_tickets": 0, "is_enterprise": False},
              "expected_min": 0.9, "expected_max": 1.0}]
    status, run = gateway.run_serving_eval(
        KEY, {"model": "churn-risk", "cases": cases, "min_pass_rate": 0.8})
    assert status == 200
    assert run["pass_rate"] == 0.0
    assert run["gate_passed"] is False


def test_serving_eval_invalid_features_fail_the_case():
    gateway = _serving_gateway()
    cases = [{"features": {"tenure_months": -5},
              "expected_min": 0.0, "expected_max": 1.0}]
    status, run = gateway.run_serving_eval(
        KEY, {"model": "churn-risk", "cases": cases})
    assert status == 200
    assert run["results"][0]["passed"] is False
    assert run["results"][0]["error"] == "validation_failed"


def test_get_unknown_serving_eval_returns_404():
    gateway = make_gateway()
    status, payload = gateway.get_serving_eval(KEY, "serving-eval-999")
    assert status == 404


# ---- Agent evaluation ----------------------------------------------------

def test_agent_eval_passes_with_traces_and_gate():
    gateway = make_gateway()
    cases = [{"prompt": "How did partner revenue trend?",
              "expected_contains": "revenue grew"},
             {"prompt": "What happened to churn this quarter?",
              "expected_contains": "churn fell"}]
    status, run = gateway.run_agent_eval(
        KEY, {"agent": "marketplace-intelligence-agent", "cases": cases})
    assert status == 200
    assert run["pass_rate"] == 1.0
    assert run["gate_passed"] is True
    assert len(run["results"][0]["trace"]) == 3
    assert run["results"][0]["trace"][0]["step"] == "retrieve"
    status, fetched = gateway.get_agent_eval(KEY, run["run_id"])
    assert status == 200
    assert fetched["agent"] == "marketplace-intelligence-agent"


def test_agent_eval_fails_when_expected_text_missing():
    gateway = make_gateway()
    cases = [{"prompt": "Tell me about revenue.",
              "expected_contains": "churn fell"}]
    status, run = gateway.run_agent_eval(
        KEY, {"agent": "marketplace-intelligence-agent", "cases": cases})
    assert status == 200
    assert run["pass_rate"] == 0.0
    assert run["gate_passed"] is False
    assert "No governed data" not in run["results"][0]["response"]


def test_agent_eval_unknown_topic_returns_no_data_response():
    gateway = make_gateway()
    cases = [{"prompt": "Tell me about office snacks.",
              "expected_contains": "No governed data"}]
    status, run = gateway.run_agent_eval(KEY, {"cases": cases})
    assert status == 200
    assert run["pass_rate"] == 1.0


def test_get_unknown_agent_eval_returns_404():
    gateway = make_gateway()
    status, payload = gateway.get_agent_eval(KEY, "agent-eval-999")
    assert status == 404


# ---- HTTP wiring ----------------------------------------------------------

def test_http_marketplace_endpoints_end_to_end():
    import json
    from http.server import ThreadingHTTPServer
    import threading
    import urllib.request

    gateway = make_gateway()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(gateway))
    server.gateway = gateway
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_address[1]

    def call(method, path, body=None, key=KEY):
        req = urllib.request.Request(
            base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    try:
        assert call("POST", "/v1/marketplace/datasets", DATASET)[0] == 201
        status, result = call("POST", "/v1/marketplace/datasets/partner-sales/ingest",
                              {"rows": ROWS})
        assert status == 200 and result["accepted"] == 3
        assert call("POST", "/v1/marketplace/semantic/metrics",
                    {"name": "total_revenue", "dataset_id": "partner-sales",
                     "column": "revenue", "aggregation": "sum"})[0] == 201
        status, answer = call("POST", "/v1/marketplace/semantic/query",
                              {"metric": "total_revenue"})
        assert status == 200 and answer["value"] == 400
        assert call("POST", "/v1/marketplace/semantic/query",
                    {"metric": "total_revenue"}, key="bad-key")[0] == 401
        status, run = call("POST", "/v1/marketplace/evals/agents",
                           {"agent": "demo-agent",
                            "cases": [{"prompt": "How is usage trending?",
                                       "expected_contains": "usage peaked"}]})
        assert status == 200 and run["gate_passed"] is True
        status, fetched = call("GET", "/v1/marketplace/evals/agents/" + run["run_id"])
        assert status == 200 and fetched["run_id"] == run["run_id"]
    finally:
        server.shutdown()
        server.server_close()
