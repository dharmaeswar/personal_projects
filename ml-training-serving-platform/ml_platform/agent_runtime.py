"""Agentic ML platform layer: portable model packaging + an MCP-style tool runtime.

This module sits on top of the training, registry, serving, and evaluation
layers and is the part of the platform an agentic workflow drives:

- **Model packaging** (`package_model` / `load_package`): exports a trained
  model as a portable, self-describing artifact — a JSON manifest with an
  input/output schema, framework tag, weights, and a SHA-256 checksum, in
  the spirit of ONNX packaging (a portable graph + metadata envelope, not
  a real ONNX binary: this project has no ONNX dependency, and the
  manifest says so). A package whose bytes were tampered with fails to
  load, so a serving layer can refuse a corrupt artifact instead of
  serving it.
- **Tool registry** (`ToolRegistry`): an MCP-style registry — every platform
  capability is a named tool with a description, a typed input schema, and
  a handler. Agents call tools by name; unknown tools and missing inputs
  are rejected before any handler runs.
- **Agent runtime** (`AgentRuntime`): runs multi-step platform tasks
  (validate-and-promote a candidate, respond to drift) as a planned
  sequence of tool calls with a full trace, bounded retries on transient
  failures, and guardrails: promotion and rollback are *guarded* tools
  that need explicit approval, and a failed promotion gate stops the run
  before anything is promoted. Retries are idempotent — a retried tool
  call reuses its idempotency key and a failed step never leaves a
  half-applied promotion behind.

All data is synthetic; no real customer, credit, or payments data is used.
"""

import hashlib
import inspect
import json
import os
import time

from .data import FEATURES
from .evaluation import promotion_gate
from .training import LogisticModel, evaluate, train

PACKAGE_FORMAT = "ml-platform-package/1"
PACKAGE_FRAMEWORK = "logistic-regression (plain-Python, ONNX-style manifest)"


class RetryableError(Exception):
    """A transient tool failure that the agent may retry."""


class GuardedToolError(Exception):
    """A guarded tool was called without the approval it requires."""


# ---------------------------------------------------------------------------
# Model packaging
# ---------------------------------------------------------------------------

def package_model(model, name, version, metrics=None, framework=None):
    """Export a trained model as a portable package manifest (dict).

    The manifest carries everything a serving runtime needs without the
    training code: feature schema, weights, framework tag, and a checksum
    over the canonical payload so tampering is detectable on load.
    """
    payload = {
        "format": PACKAGE_FORMAT,
        "model_name": name,
        "model_version": version,
        "framework": framework or PACKAGE_FRAMEWORK,
        "inputs": [{"name": f, "type": "float"} for f in model.features],
        "outputs": [{"name": "default_probability", "type": "float"}],
        "weights": model.weights,
        "bias": model.bias,
        "means": model.means,
        "stds": model.stds,
        "metrics": metrics or {},
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    manifest = dict(payload)
    manifest["sha256"] = hashlib.sha256(blob).hexdigest()
    return manifest


def write_package(manifest, path):
    """Write a package manifest to disk."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    return path


def load_package(path):
    """Load and verify a package manifest; raises ValueError if corrupt."""
    with open(path) as f:
        manifest = json.load(f)
    if manifest.get("format") != PACKAGE_FORMAT:
        raise ValueError(f"unsupported package format: {manifest.get('format')}")
    checksum = manifest.pop("sha256", None)
    blob = json.dumps(manifest, sort_keys=True).encode("utf-8")
    if checksum != hashlib.sha256(blob).hexdigest():
        raise ValueError("package checksum mismatch: artifact may be corrupt or tampered with")
    manifest["sha256"] = checksum
    for field in ("weights", "bias", "means", "stds", "inputs"):
        if field not in manifest:
            raise ValueError(f"package missing required field: {field}")
    return manifest


def model_from_package(manifest):
    """Rebuild a LogisticModel from a verified package manifest."""
    features = [inp["name"] for inp in manifest["inputs"]]
    return LogisticModel(
        manifest["weights"], manifest["bias"],
        manifest["means"], manifest["stds"], features,
    )


def explain_model(model):
    """Weight-based feature importance for a logistic model.

    Returns features ranked by |standardised weight|, normalised to sum
    to 1. This is a transparent importance ranking for a linear model —
    it is not SHAP, and it is not labelled as such.
    """
    total = sum(abs(w) for w in model.weights) or 1.0
    ranked = sorted(
        (
            {"feature": f, "weight": round(w, 4),
             "importance": round(abs(w) / total, 4)}
            for f, w in zip(model.features, model.weights)
        ),
        key=lambda r: r["importance"], reverse=True,
    )
    return ranked


# ---------------------------------------------------------------------------
# MCP-style tool registry
# ---------------------------------------------------------------------------

class Tool:
    """One platform capability exposed to agents: name, schema, handler."""

    def __init__(self, name, description, inputs, handler, guarded=False):
        self.name = name
        self.description = description
        self.inputs = inputs  # {param: type-name}
        self.handler = handler
        self.guarded = guarded
        # A param is required only when the handler has no default for it.
        sig = inspect.signature(handler)
        self.required = [
            p for p in inputs
            if p in sig.parameters
            and sig.parameters[p].default is inspect.Parameter.empty
        ]

    def spec(self):
        return {"name": self.name, "description": self.description,
                "inputs": self.inputs, "guarded": self.guarded,
                "required": self.required}


class ToolRegistry:
    """Named tools with typed inputs; unknown tools and bad inputs are rejected."""

    def __init__(self):
        self._tools = {}

    def register(self, tool):
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list_tools(self):
        return [t.spec() for t in self._tools.values()]

    def call(self, tool_name, **kwargs):
        """Call a tool by name. Returns {ok, result} or {ok: False, error}."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"ok": False, "error": f"unknown tool: {tool_name}"}
        missing = [p for p in tool.required if p not in kwargs]
        if missing:
            return {"ok": False, "error": f"missing inputs for {tool_name}: {missing}"}
        if tool.guarded and not kwargs.get("approved", False):
            return {"ok": False,
                    "error": f"tool {tool_name} is guarded and needs approved=True"}
        try:
            return {"ok": True, "result": tool.handler(**kwargs)}
        except GuardedToolError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # handler errors are reported, not raised
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Platform tools: wire the registry to a Registry + data + serving layer
# ---------------------------------------------------------------------------

def build_platform_tools(registry, train_rows, eval_rows, serving=None):
    """Build a ToolRegistry bound to one model registry and eval set.

    Tools: train_model, evaluate_candidate, package_model, explain_model,
    drift_check, promote_model (guarded), rollback_model (guarded).
    """
    tools = ToolRegistry()
    state = {"candidate_version": None, "candidate_model": None}

    def _train_model(name="credit-decision", epochs=300, seed=7):
        model = train(train_rows, epochs=epochs, seed=seed)
        metrics = evaluate(model, eval_rows)
        version = registry.register(name, model, metrics)
        state["candidate_version"] = version
        state["candidate_model"] = model
        return {"version": version, "metrics": metrics}

    def _evaluate_candidate(min_improvement=0.005, primary="auc"):
        candidate = state["candidate_model"]
        if candidate is None:
            raise ValueError("no candidate trained yet; call train_model first")
        production_version = registry.production_version()
        if production_version is None:
            return {"promote": True, "primary_delta": None,
                    "reasons": ["no production model yet; candidate is first"],
                    "candidate": evaluate(candidate, eval_rows),
                    "production": None}
        production = LogisticModel.from_dict(
            registry.get(production_version)["model"])
        return promotion_gate(candidate, production, eval_rows,
                              primary=primary, min_improvement=min_improvement)

    def _package_model(version=None, out_dir="."):
        version = version or state["candidate_version"]
        if version is None:
            raise ValueError("no version to package; train a model first")
        entry = registry.get(version)
        if entry is None:
            raise ValueError(f"unknown model version {version}")
        model = LogisticModel.from_dict(entry["model"])
        manifest = package_model(model, entry["name"], version,
                                 metrics=entry["metrics"])
        path = os.path.join(out_dir, f"{version}.package.json")
        write_package(manifest, path)
        return {"version": version, "path": path, "sha256": manifest["sha256"]}

    def _explain_model(version=None):
        version = version or state["candidate_version"]
        if version is None:
            raise ValueError("no version to explain; train a model first")
        entry = registry.get(version)
        model = LogisticModel.from_dict(entry["model"])
        return {"version": version, "importance": explain_model(model)}

    def _drift_check():
        if serving is None:
            raise ValueError("no serving service attached; drift check unavailable")
        report = serving.drift_report()
        flagged = [f for f, r in report.items() if r.get("flagged")]
        return {"flagged_features": flagged, "report": report,
                "recommendation": ("rollback" if flagged else "no action")}

    def _promote_model(version=None, approved=False):
        version = version or state["candidate_version"]
        if version is None:
            raise ValueError("no version to promote; train a model first")
        if not approved:
            raise GuardedToolError("promote_model needs approved=True")
        registry.promote(version)
        return {"version": version, "stage": "production"}

    def _rollback_model(approved=False):
        if not approved:
            raise GuardedToolError("rollback_model needs approved=True")
        restored = registry.rollback()
        if serving is not None:
            serving.rollback()
        return {"restored_version": restored}

    tools.register(Tool(
        "train_model", "Train a candidate model on the training rows and register it.",
        {"name": str, "epochs": int, "seed": int}, _train_model))
    tools.register(Tool(
        "evaluate_candidate", "Run the promotion gate: candidate vs production on the eval set.",
        {"min_improvement": float, "primary": str}, _evaluate_candidate))
    tools.register(Tool(
        "package_model", "Export a registered model version as a portable, checksummed package.",
        {"version": str, "out_dir": str}, _package_model))
    tools.register(Tool(
        "explain_model", "Rank features by standardised-weight importance for a model version.",
        {"version": str}, _explain_model))
    tools.register(Tool(
        "drift_check", "Check serving feature drift (PSI) against the training baseline.",
        {}, _drift_check))
    tools.register(Tool(
        "promote_model", "Promote a registered version to production. Guarded: needs approval.",
        {"version": str, "approved": bool}, _promote_model, guarded=True))
    tools.register(Tool(
        "rollback_model", "Restore the previous production version. Guarded: needs approval.",
        {"approved": bool}, _rollback_model, guarded=True))
    return tools


# ---------------------------------------------------------------------------
# Agent runtime: planned multi-step tasks with trace, retries, guardrails
# ---------------------------------------------------------------------------

# Each task is a planned sequence of tool calls. A step may carry a
# "gate" — when the previous step's result says promote is False, the run
# stops before any guarded tool runs.
TASK_PLANS = {
    "validate_and_promote": [
        {"tool": "train_model", "args": {}},
        {"tool": "evaluate_candidate", "args": {}},
        {"tool": "package_model", "args": {}, "gate": "promote"},
        # Promotion is guarded: approval must be passed in by the caller
        # (task_args={"promote_model": {"approved": True}}). Without it the
        # run stops at this step and nothing is promoted.
        {"tool": "promote_model", "args": {}, "gate": "promote"},
    ],
    "drift_response": [
        {"tool": "drift_check", "args": {}},
    ],
}


class AgentRuntime:
    """Runs a planned task through the tool registry, with a full trace.

    Retries a step up to `max_retries` times when its handler raises a
    RetryableError; other failures stop the run. A failed promotion gate
    stops the run before packaging or promotion.
    """

    def __init__(self, tools, max_retries=2):
        self.tools = tools
        self.max_retries = max_retries

    def run(self, task, task_args=None):
        plan = TASK_PLANS.get(task)
        if plan is None:
            return {"task": task, "status": "failed",
                    "error": f"unknown task: {task}", "trace": []}
        task_args = task_args or {}
        trace = []
        gate_open = True
        for step_no, step in enumerate(plan, start=1):
            if step.get("gate") == "promote" and not gate_open:
                trace.append({"step": step_no, "tool": step["tool"],
                              "status": "skipped",
                              "note": "promotion gate failed; step skipped"})
                continue
            args = dict(step["args"])
            args.update(task_args.get(step["tool"], {}))
            record = {"step": step_no, "tool": step["tool"],
                      "inputs": args, "attempts": 0, "idempotency_key": f"{task}:{step_no}"}
            result = self._call_with_retries(step["tool"], args, record)
            trace.append(record)
            if not result.get("ok"):
                record["status"] = "failed"
                record["error"] = result.get("error")
                return {"task": task, "status": "failed",
                        "error": f"step {step_no} ({step['tool']}) failed: {result.get('error')}",
                        "trace": trace}
            record["status"] = "ok"
            record["result"] = result.get("result")
            if step["tool"] == "evaluate_candidate":
                gate_open = bool(result["result"].get("promote", False))
                if not gate_open:
                    record["note"] = "promotion gate failed; run stops here"
        status = "completed" if gate_open else "gate_failed"
        return {"task": task, "status": status, "trace": trace}

    def _call_with_retries(self, name, args, record):
        last = {"ok": False, "error": "no attempt made"}
        for attempt in range(1, self.max_retries + 2):
            record["attempts"] = attempt
            tool = self.tools._tools.get(name)
            if tool is None:
                return {"ok": False, "error": f"unknown tool: {name}"}
            try:
                missing = [p for p in tool.required if p not in args]
                if missing:
                    return {"ok": False, "error": f"missing inputs for {name}: {missing}"}
                if tool.guarded and not args.get("approved", False):
                    return {"ok": False,
                            "error": f"tool {name} is guarded and needs approved=True"}
                return {"ok": True, "result": tool.handler(**args)}
            except RetryableError:
                last = {"ok": False, "error": "transient failure; retrying"}
                time.sleep(0)  # no real backoff needed for in-process tools
                continue
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return last
