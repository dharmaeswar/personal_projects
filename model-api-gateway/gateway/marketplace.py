"""Marketplace partner intelligence module for the Model API Gateway.

Extension for the AWS Marketplace & Partner Services (AMPS) Data &
Analytics Engineering role: partner data ingestion into a governed
semantic layer, a model-serving evaluation foundation, and an
agent-evaluation foundation, plus self-serve intelligence-delivery
API endpoints (wired up in ``gateway/api.py``).

Everything here is an in-memory stand-in: datasets, semantic
definitions, eval runs, and traces live in process memory only.
There is no real database, message broker, or model host behind it —
a production deployment would persist datasets in a warehouse, the
semantic layer in a governed catalog, and eval runs in a results
store, and would call real model endpoints instead of the demo
scorer / demo agent below. Nothing here claims production ownership
or real partner data: all datasets, partners, and figures are
synthetic and seeded by the caller.
"""

import itertools
import math

# ---------------------------------------------------------------------------
# Partner data ingestion + governed semantic layer
# ---------------------------------------------------------------------------

COLUMN_TYPES = ("number", "string", "boolean")


class ColumnSpec:
    """One column of a partner dataset: name, type, required flag."""

    def __init__(self, name, type="string", required=True):
        if type not in COLUMN_TYPES:
            raise ValueError("unknown column type: %r" % (type,))
        self.name = name
        self.type = type
        self.required = bool(required)

    def to_dict(self):
        return {"name": self.name, "type": self.type,
                "required": self.required}

    @classmethod
    def from_dict(cls, data):
        return cls(data["name"], data.get("type", "string"),
                   data.get("required", True))


class PartnerDataset:
    """A registered partner dataset with a fixed schema and ingested rows."""

    def __init__(self, dataset_id, name, owner_partner, columns):
        if not dataset_id or not name:
            raise ValueError("dataset id and name are required")
        self.dataset_id = dataset_id
        self.name = name
        self.owner_partner = owner_partner
        self.columns = [c if isinstance(c, ColumnSpec) else ColumnSpec.from_dict(c)
                        for c in columns]
        self.rows = []

    def validate_row(self, row):
        """Return a list of schema errors for one row (empty when valid)."""
        errors = []
        if not isinstance(row, dict):
            return ["row must be a JSON object"]
        known = {c.name: c for c in self.columns}
        for key in row:
            if key not in known:
                errors.append("unknown column: %s" % key)
        for spec in self.columns:
            value = row.get(spec.name)
            if value is None:
                if spec.required:
                    errors.append("missing required column: %s" % spec.name)
                continue
            if spec.type == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append("column %s must be a number" % spec.name)
            elif spec.type == "string":
                if not isinstance(value, str):
                    errors.append("column %s must be a string" % spec.name)
            elif spec.type == "boolean":
                if not isinstance(value, bool):
                    errors.append("column %s must be a boolean" % spec.name)
        return errors

    def to_dict(self):
        return {"dataset_id": self.dataset_id, "name": self.name,
                "owner_partner": self.owner_partner,
                "columns": [c.to_dict() for c in self.columns],
                "row_count": len(self.rows)}


AGGREGATIONS = ("sum", "avg", "count", "min", "max")


class SemanticMetric:
    """One governed metric: an aggregation over a dataset column.

    The metric is the single trustworthy definition teams query
    instead of writing their own SQL — the semantic layer resolves it
    against the registered dataset and records lineage (dataset,
    column, filters) with every answer.
    """

    def __init__(self, name, dataset_id, column, aggregation, description=""):
        if aggregation not in AGGREGATIONS:
            raise ValueError("unknown aggregation: %r" % (aggregation,))
        self.name = name
        self.dataset_id = dataset_id
        self.column = column
        self.aggregation = aggregation
        self.description = description

    def to_dict(self):
        return {"name": self.name, "dataset_id": self.dataset_id,
                "column": self.column, "aggregation": self.aggregation,
                "description": self.description}


def _row_matches(row, filters):
    return all(row.get(k) == v for k, v in (filters or {}).items())


class MarketplaceStore:
    """In-memory store: datasets, semantic metrics, and eval runs."""

    def __init__(self):
        self.datasets = {}          # dataset_id -> PartnerDataset
        self.metrics = {}           # metric name -> SemanticMetric
        self.serving_eval_runs = {}  # run_id -> dict
        self.agent_eval_runs = {}    # run_id -> dict
        self._run_seq = itertools.count(1)

    # ---- Datasets ------------------------------------------------------
    def register_dataset(self, dataset_id, name, owner_partner, columns):
        if dataset_id in self.datasets:
            raise ValueError("dataset %s already registered" % dataset_id)
        dataset = PartnerDataset(dataset_id, name, owner_partner, columns)
        self.datasets[dataset_id] = dataset
        return dataset

    def ingest(self, dataset_id, rows):
        """Validate and append rows; returns accepted/rejected counts + errors."""
        dataset = self.datasets.get(dataset_id)
        if dataset is None:
            raise ValueError("unknown dataset: %s" % dataset_id)
        accepted, rejected, errors = 0, 0, []
        for i, row in enumerate(rows or []):
            row_errors = dataset.validate_row(row)
            if row_errors:
                rejected += 1
                errors.append({"row_index": i, "errors": row_errors})
            else:
                dataset.rows.append(dict(row))
                accepted += 1
        return {"dataset_id": dataset_id, "accepted": accepted,
                "rejected": rejected, "row_count": len(dataset.rows),
                "errors": errors}

    # ---- Governed semantic layer ---------------------------------------
    def define_metric(self, name, dataset_id, column, aggregation,
                      description=""):
        if name in self.metrics:
            raise ValueError("metric %s already defined" % name)
        dataset = self.datasets.get(dataset_id)
        if dataset is None:
            raise ValueError("unknown dataset: %s" % dataset_id)
        known = {c.name for c in dataset.columns}
        if column != "*" and column not in known:
            raise ValueError("unknown column %s for dataset %s"
                             % (column, dataset_id))
        metric = SemanticMetric(name, dataset_id, column, aggregation,
                                description)
        self.metrics[name] = metric
        return metric

    def query_metric(self, name, filters=None):
        """Resolve a governed metric; returns value, rows used, lineage."""
        metric = self.metrics.get(name)
        if metric is None:
            raise ValueError("unknown metric: %s" % name)
        dataset = self.datasets[metric.dataset_id]
        rows = [r for r in dataset.rows if _row_matches(r, filters)]
        if metric.aggregation == "count":
            value = len(rows)
        else:
            values = [r[metric.column] for r in rows
                      if isinstance(r.get(metric.column), (int, float))
                      and not isinstance(r.get(metric.column), bool)]
            if not values:
                value = None
            elif metric.aggregation == "sum":
                value = sum(values)
            elif metric.aggregation == "avg":
                value = sum(values) / len(values)
            elif metric.aggregation == "min":
                value = min(values)
            elif metric.aggregation == "max":
                value = max(values)
        return {"metric": metric.name, "value": value,
                "rows_matched": len(rows),
                "lineage": {"dataset_id": metric.dataset_id,
                            "column": metric.column,
                            "aggregation": metric.aggregation,
                            "filters": filters or {}}}


# ---------------------------------------------------------------------------
# Model-serving evaluation foundation
# ---------------------------------------------------------------------------

class ServingEvalRun:
    """One evaluation run of a served model against expected ranges.

    Each case gives input features plus the prediction range the
    served model must land in. A case passes when the model serves a
    prediction inside its range; validation failures and unknown
    models fail the case. The run passes its gate when the pass rate
    meets ``min_pass_rate``.
    """

    def __init__(self, run_id, model, cases, min_pass_rate=0.8):
        self.run_id = run_id
        self.model = model
        self.cases = cases
        self.min_pass_rate = min_pass_rate
        self.results = []
        self.pass_rate = 0.0
        self.gate_passed = False

    def execute(self, scorer):
        passed = 0
        for case in self.cases:
            features = case.get("features", {})
            status, payload = scorer.score(
                self.model, features, version=case.get("version"))
            if status != 200:
                self.results.append({"case": case, "passed": False,
                                     "error": payload.get("error"),
                                     "details": payload.get("details")})
                continue
            prediction = payload["prediction"]
            ok = (case.get("expected_min", -math.inf) <= prediction
                  <= case.get("expected_max", math.inf))
            passed += 1 if ok else 0
            self.results.append({"case": case, "passed": ok,
                                 "prediction": prediction,
                                 "serving_version": payload["version"]})
        total = len(self.cases)
        self.pass_rate = (passed / total) if total else 0.0
        self.gate_passed = bool(total) and self.pass_rate >= self.min_pass_rate
        return self.to_dict()

    def to_dict(self):
        return {"run_id": self.run_id, "model": self.model,
                "min_pass_rate": self.min_pass_rate,
                "pass_rate": round(self.pass_rate, 4),
                "gate_passed": self.gate_passed,
                "cases_run": len(self.results),
                "results": self.results}


# ---------------------------------------------------------------------------
# Agent-evaluation foundation
# ---------------------------------------------------------------------------

DEMO_KNOWLEDGE = {
    "revenue": "revenue grew 12% quarter over quarter",
    "churn": "churn fell to 4.1% after the new onboarding flow",
    "usage": "usage peaked at 3,200 requests per minute",
}


def demo_agent(prompt):
    """Deterministic demo agent stand-in.

    Answers only from the small governed-knowledge table above, so
    its behaviour is reproducible and its limits are explicit: a real
    agent would retrieve from the semantic layer and call tools, and
    would be evaluated the same way (prompt in, trace out, expected
    content checked). Returns (response_text, trace_steps).
    """
    lowered = (prompt or "").lower()
    facts = [fact for key, fact in DEMO_KNOWLEDGE.items() if key in lowered]
    trace = [
        {"step": "retrieve", "detail": "semantic layer lookup for prompt keywords"},
        {"step": "reason", "detail": "%d governed fact(s) matched" % len(facts)},
        {"step": "respond", "detail": "composed answer from matched facts only"},
    ]
    if facts:
        return "Marketplace intelligence: " + "; ".join(facts) + ".", trace
    return "No governed data found for this request.", trace


class AgentEvalRun:
    """One evaluation run of an agent against expected-content cases.

    Each case gives a prompt plus the text the agent's answer must
    contain. A case passes when the answer contains that text. Every
    case records the agent's trace so a failure can be debugged step
    by step. The run passes its gate when the pass rate meets
    ``min_pass_rate``.
    """

    def __init__(self, run_id, agent_name, cases, min_pass_rate=0.8):
        self.run_id = run_id
        self.agent_name = agent_name
        self.cases = cases
        self.min_pass_rate = min_pass_rate
        self.results = []
        self.pass_rate = 0.0
        self.gate_passed = False

    def execute(self, agent_fn=None):
        agent_fn = agent_fn or demo_agent
        passed = 0
        for case in self.cases:
            response, trace = agent_fn(case.get("prompt", ""))
            expected = case.get("expected_contains", "")
            ok = expected in response
            passed += 1 if ok else 0
            self.results.append({"case": case, "passed": ok,
                                 "response": response, "trace": trace})
        total = len(self.cases)
        self.pass_rate = (passed / total) if total else 0.0
        self.gate_passed = bool(total) and self.pass_rate >= self.min_pass_rate
        return self.to_dict()

    def to_dict(self):
        return {"run_id": self.run_id, "agent": self.agent_name,
                "min_pass_rate": self.min_pass_rate,
                "pass_rate": round(self.pass_rate, 4),
                "gate_passed": self.gate_passed,
                "cases_run": len(self.results),
                "results": self.results}


def run_serving_eval(store, scorer, model, cases, min_pass_rate=0.8):
    run_id = "serving-eval-%d" % next(store._run_seq)
    run = ServingEvalRun(run_id, model, cases, min_pass_rate)
    store.serving_eval_runs[run_id] = run
    return run.execute(scorer)


def run_agent_eval(store, agent_name, cases, min_pass_rate=0.8,
                   agent_fn=None):
    run_id = "agent-eval-%d" % next(store._run_seq)
    run = AgentEvalRun(run_id, agent_name, cases, min_pass_rate)
    store.agent_eval_runs[run_id] = run
    return run.execute(agent_fn)
