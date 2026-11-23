"""Identity analytics: ingestion, transformation, serving, quality (stdlib only).

Models the data-platform side of an AWS Identity Analytics-style service:
raw IAM/STS-style auth events arrive from many identity services, are
validated and de-duplicated on ingest, transformed into structured,
queryable per-principal features, and served to ML models and LLM agents
through a feature-lookup and query API. Data quality and freshness are
checked continuously: invalid events are rejected and counted, stale
source services raise alerts, and a quality summary reports the state of
the pipeline.

What is real here: the validation, de-duplication, feature aggregation,
freshness math, alerting rules, HTTP API and tests all run locally with
the Python 3.11+ standard library only.

What is simulated / a stand-in: there is no real Kafka broker, no
petabyte-scale store and no real IAM/STS feed. Events are held in an
in-memory store (a stand-in for a real ingestion pipeline and warehouse);
the feature store is computed from those in-memory events (a stand-in
for a real feature store); the serving API is the same shape a real
model-serving layer would expose. Nothing here contacts AWS.
"""

from __future__ import annotations

import itertools
import threading

from .models import ValidationError

# Identity services whose auth events this pipeline ingests.
IDENTITY_SERVICES = ("iam", "sts", "cognito", "sso", "directory")
OUTCOMES = ("success", "denied", "error")
# A source service is stale when its newest event lags the newest event
# seen anywhere by more than this many seconds.
FRESHNESS_THRESHOLD_SECONDS = 3600
# A principal whose denied share of events is at or above this rate is
# flagged as high-denial in its feature record.
HIGH_DENIAL_RATE = 0.5
MAX_EVENT_ID_LEN = 128
MAX_PRINCIPAL_LEN = 128
# Timestamps more than this far in the future are rejected as bad data
# (clock skew allowance, seconds).
MAX_FUTURE_SKEW_SECONDS = 300


def validate_event(body: dict, now: int | None = None) -> dict:
    """Validate one raw identity event. Returns a cleaned dict or raises."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    event_id = body.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValidationError("event_id is required")
    if len(event_id) > MAX_EVENT_ID_LEN:
        raise ValidationError("event_id is too long")
    principal = body.get("principal")
    if not isinstance(principal, str) or not principal.strip():
        raise ValidationError("principal is required")
    if len(principal) > MAX_PRINCIPAL_LEN:
        raise ValidationError("principal is too long")
    service = body.get("service")
    if service not in IDENTITY_SERVICES:
        raise ValidationError(
            f"service must be one of {', '.join(IDENTITY_SERVICES)}"
        )
    action = body.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValidationError("action is required")
    outcome = body.get("outcome")
    if outcome not in OUTCOMES:
        raise ValidationError(
            f"outcome must be one of {', '.join(OUTCOMES)}"
        )
    timestamp = body.get("timestamp")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        raise ValidationError("timestamp must be an integer epoch second")
    if timestamp < 0:
        raise ValidationError("timestamp must be zero or positive")
    if now is not None and timestamp > now + MAX_FUTURE_SKEW_SECONDS:
        raise ValidationError("timestamp is too far in the future")
    source_ip = body.get("source_ip", "")
    if not isinstance(source_ip, str):
        raise ValidationError("source_ip must be a string")
    region = body.get("region", "")
    if not isinstance(region, str):
        raise ValidationError("region must be a string")
    return {
        "event_id": event_id.strip(),
        "principal": principal.strip(),
        "service": service,
        "action": action.strip(),
        "outcome": outcome,
        "timestamp": timestamp,
        "source_ip": source_ip,
        "region": region,
    }


def validate_query(body: dict) -> dict:
    """Validate a serving-layer query for ML models / LLM agents."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    filters: dict = {}
    for field in ("principal", "service", "action", "outcome"):
        value = body.get(field)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{field} must be a non-empty string")
            filters[field] = value.strip()
    if "service" in filters and filters["service"] not in IDENTITY_SERVICES:
        raise ValidationError(
            f"service must be one of {', '.join(IDENTITY_SERVICES)}"
        )
    if "outcome" in filters and filters["outcome"] not in OUTCOMES:
        raise ValidationError(
            f"outcome must be one of {', '.join(OUTCOMES)}"
        )
    limit = body.get("limit", 50)
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValidationError("limit must be an integer")
    if limit < 1 or limit > 500:
        raise ValidationError("limit must be between 1 and 500")
    return {"filters": filters, "limit": limit}


def build_features(principal: str, events: list[dict]) -> dict:
    """Transform raw events for one principal into a queryable feature record.

    Features: event counts by outcome, denial rate, distinct services and
    actions touched, and first/last seen timestamps. A model or agent
    reads this record instead of scanning raw logs.
    """
    total = len(events)
    denied = sum(1 for e in events if e["outcome"] == "denied")
    errors = sum(1 for e in events if e["outcome"] == "error")
    successes = total - denied - errors
    timestamps = [e["timestamp"] for e in events]
    return {
        "principal": principal,
        "total_events": total,
        "success_events": successes,
        "denied_events": denied,
        "error_events": errors,
        "denial_rate": round(denied / total, 4) if total else 0.0,
        "high_denial": (denied / total) >= HIGH_DENIAL_RATE if total else False,
        "distinct_services": sorted({e["service"] for e in events}),
        "distinct_actions": sorted({e["action"] for e in events}),
        "first_seen": min(timestamps) if timestamps else None,
        "last_seen": max(timestamps) if timestamps else None,
    }


class IdentityStore:
    """Thread-safe in-memory identity-event store and feature/quality layer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, dict] = {}
        self._order: list[str] = []
        self._duplicates = 0
        self._rejected = 0
        self._rejections: list[dict] = []
        self._alerts: list[dict] = []
        self._alert_counter = itertools.count(1)
        self._stale_alerted: set[str] = set()

    def ingest(self, cleaned: dict) -> tuple[dict, bool]:
        """Store one validated event. Returns (record, is_duplicate)."""
        with self._lock:
            event_id = cleaned["event_id"]
            if event_id in self._events:
                self._duplicates += 1
                return dict(self._events[event_id]), True
            record = dict(cleaned)
            self._events[event_id] = record
            self._order.append(event_id)
            # A fresh event from a service resolves its staleness alert.
            for alert in self._alerts:
                if (
                    alert["service"] == record["service"]
                    and alert["type"] == "stale_service"
                    and alert["status"] == "active"
                ):
                    alert["status"] = "resolved"
            self._stale_alerted.discard(record["service"])
            return dict(record), False

    def ingest_batch(self, raw_events, now: int | None = None) -> dict:
        """Ingest a batch of raw events; invalid ones are counted, not lost silently."""
        accepted = 0
        duplicates = 0
        rejected = 0
        errors: list[dict] = []
        if not isinstance(raw_events, list):
            raise ValidationError("events must be a list")
        for raw in raw_events:
            try:
                cleaned = validate_event(raw, now=now)
            except ValidationError as exc:
                rejected += 1
                with self._lock:
                    self._rejected += 1
                    self._rejections.append(
                        {"event": raw if isinstance(raw, dict) else str(raw), "error": str(exc)}
                    )
                errors.append({"error": str(exc)})
                continue
            _, is_dup = self.ingest(cleaned)
            if is_dup:
                duplicates += 1
            else:
                accepted += 1
        return {
            "accepted": accepted,
            "duplicates": duplicates,
            "rejected": rejected,
            "errors": errors,
        }

    def events(self, filters: dict | None = None, limit: int | None = None) -> list[dict]:
        """Raw events in ingest order, optionally filtered (serving-layer read)."""
        with self._lock:
            records = [dict(self._events[eid]) for eid in self._order]
        if filters:
            records = [
                r for r in records
                if all(r.get(k) == v for k, v in filters.items())
            ]
        if limit is not None:
            records = records[:limit]
        return records

    def features(self, principal: str) -> dict | None:
        """Feature record for one principal, or None if never seen."""
        mine = self.events({"principal": principal})
        if not mine:
            return None
        return build_features(principal, mine)

    def query(self, filters: dict, limit: int) -> dict:
        """Filtered event query for ML models / LLM agents."""
        matched = self.events(filters)
        return {
            "count": len(matched),
            "returned": len(matched[:limit]),
            "events": matched[:limit],
        }

    def quality_summary(self) -> dict:
        """Data quality and freshness: counts plus per-service staleness."""
        with self._lock:
            total = len(self._events)
            duplicates = self._duplicates
            rejected = self._rejected
            per_service: dict[str, dict] = {}
            newest_overall: int | None = None
            for record in self._events.values():
                entry = per_service.setdefault(
                    record["service"], {"count": 0, "latest_timestamp": None}
                )
                entry["count"] += 1
                if (
                    entry["latest_timestamp"] is None
                    or record["timestamp"] > entry["latest_timestamp"]
                ):
                    entry["latest_timestamp"] = record["timestamp"]
                if newest_overall is None or record["timestamp"] > newest_overall:
                    newest_overall = record["timestamp"]
            for service, entry in per_service.items():
                lag = (
                    newest_overall - entry["latest_timestamp"]
                    if newest_overall is not None
                    else 0
                )
                entry["lag_seconds"] = lag
                entry["stale"] = lag > FRESHNESS_THRESHOLD_SECONDS
        invalid_rate = round(rejected / (total + rejected), 4) if (total + rejected) else 0.0
        return {
            "total_events": total,
            "duplicates": duplicates,
            "rejected": rejected,
            "invalid_rate": invalid_rate,
            "freshness_threshold_seconds": FRESHNESS_THRESHOLD_SECONDS,
            "per_service": per_service,
            "active_alerts": [a for a in self._alerts if a["status"] == "active"],
        }

    def check_freshness(self) -> list[dict]:
        """Raise one alert per stale source service; returns active alerts."""
        summary = self.quality_summary()
        with self._lock:
            for service, entry in summary["per_service"].items():
                if entry["stale"] and service not in self._stale_alerted:
                    alert = {
                        "id": f"ialrt_{next(self._alert_counter):06d}",
                        "type": "stale_service",
                        "service": service,
                        "status": "active",
                        "message": (
                            f"{service} is stale: latest event lags the "
                            f"newest event by {entry['lag_seconds']}s, over the "
                            f"{FRESHNESS_THRESHOLD_SECONDS}s threshold"
                        ),
                    }
                    self._alerts.append(alert)
                    self._stale_alerted.add(service)
            return [a for a in self._alerts if a["status"] == "active"]

    def active_alerts(self) -> list[dict]:
        with self._lock:
            return [dict(a) for a in self._alerts if a["status"] == "active"]

    def count(self) -> int:
        with self._lock:
            return len(self._events)
