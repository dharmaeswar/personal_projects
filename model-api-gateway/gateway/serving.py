"""Predictive-model serving: registry, input validation, scoring, metrics.

A model version is registered with an explicit input schema (named
features with types, required flags, and numeric ranges) and a
deterministic demo scoring rule. Scoring validates every request
against the schema before any arithmetic runs, records per-model
latency and error counts, and returns the model version that served
the request so callers can reproduce the result.

This is a demo scorer: weights are fixed per feature position and the
score is a plain weighted sum passed through a sigmoid. It stands in
for a loaded model artifact (a real deployment would load the
artifact — a pickle, ONNX file, or H2O MOJO — and call its predict
method here instead). Nothing here claims production model ownership.
"""

import math
import threading

from .observability import Metrics, percentile


class FeatureSpec:
    """One expected input feature: name, type, required, numeric bounds."""

    TYPES = ("number", "string", "boolean")

    def __init__(self, name, type="number", required=True, minimum=None, maximum=None):
        if type not in self.TYPES:
            raise ValueError("unknown feature type: %r" % (type,))
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum %r above maximum %r" % (minimum, maximum))
        self.name = name
        self.type = type
        self.required = bool(required)
        self.minimum = minimum
        self.maximum = maximum

    def to_dict(self):
        return {"name": self.name, "type": self.type,
                "required": self.required,
                "minimum": self.minimum, "maximum": self.maximum}

    @classmethod
    def from_dict(cls, data):
        return cls(data["name"], data.get("type", "number"),
                   data.get("required", True),
                   data.get("minimum"), data.get("maximum"))


class ModelVersion:
    """One registered version of a predictive model."""

    def __init__(self, name, version, framework, features, target,
                 artifact="demo://%s", description=""):
        if not name or not version:
            raise ValueError("model name and version are required")
        self.name = name
        self.version = str(version)
        self.framework = framework
        self.features = [f if isinstance(f, FeatureSpec) else FeatureSpec.from_dict(f)
                         for f in features]
        self.target = target
        self.artifact = artifact % (name,) if "%s" in artifact else artifact
        self.description = description

    def to_dict(self):
        return {"name": self.name, "version": self.version,
                "framework": self.framework,
                "features": [f.to_dict() for f in self.features],
                "target": self.target, "artifact": self.artifact,
                "description": self.description}


def _version_key(version):
    """Sort key for dotted numeric versions (1.10 sorts after 1.2)."""
    parts = []
    for chunk in str(version).split("."):
        try:
            parts.append((0, int(chunk), ""))
        except ValueError:
            parts.append((1, 0, chunk))
    return parts


class ModelRegistry:
    """Registry of predictive model versions, keyed by (name, version)."""

    def __init__(self):
        self._versions = {}  # (name, version) -> ModelVersion
        self._lock = threading.Lock()

    def register(self, model_version):
        """Register a version; duplicate (name, version) is an error."""
        key = (model_version.name, model_version.version)
        with self._lock:
            if key in self._versions:
                raise ValueError("model %s version %s already registered"
                                 % (model_version.name, model_version.version))
            self._versions[key] = model_version
        return model_version

    def get(self, name, version=None):
        """Fetch a version, or the latest version when none is given."""
        with self._lock:
            if version is not None:
                return self._versions.get((name, str(version)))
            matches = [v for (n, _), v in self._versions.items() if n == name]
        if not matches:
            return None
        return max(matches, key=lambda v: _version_key(v.version))

    def models(self):
        """List registered models: [{name, versions[], latest}]."""
        with self._lock:
            names = sorted({n for (n, _) in self._versions})
            versions = {n: sorted([v for (m, v) in self._versions if m == n],
                                  key=_version_key)
                        for n in names}
        out = []
        for name in names:
            latest = self.get(name)
            out.append({"name": name, "versions": versions[name],
                        "latest": latest.version if latest else None,
                        "framework": latest.framework if latest else None,
                        "target": latest.target if latest else None})
        return out

    def validate(self, model_version, features):
        """Validate a feature dict against the model's schema.

        Returns a list of error strings (empty when the input is valid).
        Unknown extra features are rejected so a renamed or mistyped
        field fails loudly instead of being silently ignored.
        """
        errors = []
        if not isinstance(features, dict):
            return ["features must be a JSON object"]
        known = {f.name: f for f in model_version.features}
        for name in features:
            if name not in known:
                errors.append("unknown feature: %s" % name)
        for spec in model_version.features:
            value = features.get(spec.name)
            if value is None:
                if spec.required:
                    errors.append("missing required feature: %s" % spec.name)
                continue
            if spec.type == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append("feature %s must be a number" % spec.name)
                elif spec.minimum is not None and value < spec.minimum:
                    errors.append("feature %s below minimum %s" % (spec.name, spec.minimum))
                elif spec.maximum is not None and value > spec.maximum:
                    errors.append("feature %s above maximum %s" % (spec.name, spec.maximum))
            elif spec.type == "string":
                if not isinstance(value, str):
                    errors.append("feature %s must be a string" % spec.name)
            elif spec.type == "boolean":
                if not isinstance(value, bool):
                    errors.append("feature %s must be a boolean" % spec.name)
        return errors


def demo_score(model_version, features):
    """Deterministic demo score: weighted sum of numeric features, sigmoided.

    Weights are fixed per feature position (0.5, -0.25, 0.125, ...), and
    each numeric value is squashed to (-1, 1) first, so raw feature
    scales cannot push the sum to an extreme and the score stays a
    meaningful probability. The same input always yields the same score.
    """
    total = 0.0
    for i, spec in enumerate(model_version.features):
        value = features.get(spec.name)
        if spec.type == "number" and isinstance(value, (int, float)):
            weight = 0.5 * ((-0.5) ** i)
            total += weight * (float(value) / (1.0 + abs(float(value))))
        elif spec.type == "boolean" and isinstance(value, bool):
            total += 0.25 if value else -0.25
    return 1.0 / (1.0 + math.exp(-total))


class ServingMetrics:
    """Per-model serving stats: requests, errors, latency p50/p95."""

    def __init__(self):
        self._metrics = Metrics()

    def record(self, model, latency_ms, error=False):
        self._metrics.observe(model, latency_ms, error=error)

    def summary(self, model):
        return self._metrics.summary(model)

    def summary_all(self):
        return {m: self._metrics.summary(m)
                for m in sorted(self._metrics._total)}

    def evaluate_slo(self, model, p95_budget_ms=500.0, error_budget=0.01):
        return self._metrics.evaluate_slo(model, p95_budget_ms, error_budget)


class Scorer:
    """Scores validated requests against a registered model version."""

    def __init__(self, registry=None, metrics=None):
        self.registry = registry or ModelRegistry()
        self.metrics = metrics or ServingMetrics()

    def score(self, name, features, version=None):
        """Validate, score, and record metrics.

        Returns (status_code, payload). 404 unknown model/version,
        422 validation errors, 200 with prediction + serving version.
        """
        model_version = self.registry.get(name, version)
        if model_version is None:
            self.metrics.record(name, 0.0, error=True)
            return 404, {"error": "unknown_model",
                         "model": name, "version": version}
        errors = self.registry.validate(model_version, features)
        if errors:
            self.metrics.record(name, 0.0, error=True)
            return 422, {"error": "validation_failed", "details": errors,
                         "model": name, "version": model_version.version}
        # Simulated inference latency: 2ms per feature + 5ms base.
        latency_ms = 5.0 + 2.0 * len(model_version.features)
        prediction = demo_score(model_version, features)
        self.metrics.record(name, latency_ms)
        return 200, {
            "model": name,
            "version": model_version.version,
            "prediction": round(prediction, 6),
            "target": model_version.target,
            "latency_ms": latency_ms,
        }
