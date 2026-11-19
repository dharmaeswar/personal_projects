"""Serving layer: prediction service with canary rollout, latency tracking,
drift checks, and rollback.

Canary routing is deterministic per application id (hash-based), so the
same application always hits the same version during a rollout. Drift is
measured with population stability index (PSI) per feature against the
training baseline; PSI above 0.25 flags a feature.
"""

import hashlib
import time

from .data import FEATURES
from .training import LogisticModel

PSI_FLAG_THRESHOLD = 0.25


def _psi(expected, actual, bins=10):
    """Population stability index between two numeric samples."""
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi == lo:
        return 0.0
    edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
    psi = 0.0
    for i in range(bins):
        e = sum(1 for v in expected if edges[i] <= v < edges[i + 1] or (i == bins - 1 and v == hi))
        a = sum(1 for v in actual if edges[i] <= v < edges[i + 1] or (i == bins - 1 and v == hi))
        e_share = max(e / len(expected), 1e-4)
        a_share = max(a / len(actual), 1e-4)
        psi += (a_share - e_share) * _log(a_share / e_share)
    return psi


def _log(x):
    import math

    return math.log(x)


class ServingService:
    def __init__(self, registry, baseline_rows):
        self.registry = registry
        self.baseline = {f: [r[0][f] for r in baseline_rows] for f in FEATURES}
        self.canary_version = None
        self.canary_share = 0.0
        self.latencies_ms = []
        self.requests = 0
        self.errors = 0
        self.seen_features = {f: [] for f in FEATURES}

    def _load_model(self, version):
        entry = self.registry.get(version)
        if entry is None:
            raise ValueError(f"unknown model version {version}")
        return LogisticModel.from_dict(entry["model"])

    def _route(self, application_id):
        if not self.canary_version or self.canary_share <= 0:
            return self.registry.production_version()
        digest = int(hashlib.sha256(str(application_id).encode()).hexdigest(), 16)
        return self.canary_version if (digest % 100) < self.canary_share * 100 else self.registry.production_version()

    def start_canary(self, version, share=0.1):
        if self.registry.get(version) is None:
            raise ValueError(f"unknown model version {version}")
        if not 0 < share <= 1:
            raise ValueError("canary share must be in (0, 1]")
        self.canary_version = version
        self.canary_share = share

    def stop_canary(self):
        self.canary_version = None
        self.canary_share = 0.0

    def predict(self, application_id, features):
        start = time.perf_counter()
        self.requests += 1
        try:
            version = self._route(application_id)
            if version is None:
                raise ValueError("no production model registered")
            model = self._load_model(version)
            score = model.predict_proba(features)
            for f in FEATURES:
                self.seen_features[f].append(features[f])
            return {"application_id": application_id, "version": version,
                    "default_probability": round(score, 4),
                    "decision": "decline" if score >= 0.5 else "approve"}
        except Exception:
            self.errors += 1
            raise
        finally:
            self.latencies_ms.append((time.perf_counter() - start) * 1000)

    def latency_stats(self):
        if not self.latencies_ms:
            return {"count": 0, "mean_ms": 0.0, "p95_ms": 0.0}
        ordered = sorted(self.latencies_ms)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        return {"count": len(ordered), "mean_ms": round(sum(ordered) / len(ordered), 3),
                "p95_ms": round(p95, 3)}

    def error_rate(self):
        return self.errors / self.requests if self.requests else 0.0

    def drift_report(self):
        report = {}
        for f in FEATURES:
            seen = self.seen_features[f]
            if len(seen) < 30:
                report[f] = {"psi": None, "flagged": False, "note": "not enough traffic yet"}
                continue
            psi = _psi(self.baseline[f], seen)
            report[f] = {"psi": round(psi, 4), "flagged": psi > PSI_FLAG_THRESHOLD,
                         "note": "drift detected" if psi > PSI_FLAG_THRESHOLD else "stable"}
        return report

    def rollback(self):
        """Restore the previous production version and stop any canary."""
        self.stop_canary()
        return self.registry.rollback()
