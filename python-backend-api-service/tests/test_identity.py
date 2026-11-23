"""Tests for the identity analytics module (ingest, transform, serve, quality)."""

import json
import threading
import urllib.request

import pytest

from payments_api.app import create_server
from payments_api.identity import (
    IdentityStore,
    build_features,
    validate_event,
    validate_query,
)
from payments_api.models import ValidationError

NOW = 1_700_000_000


def _event(**overrides):
    event = {
        "event_id": "evt_001",
        "principal": "alice",
        "service": "iam",
        "action": "AssumeRole",
        "outcome": "success",
        "timestamp": NOW,
        "source_ip": "10.0.0.1",
        "region": "us-east-1",
    }
    event.update(overrides)
    return event


class TestValidation:
    def test_valid_event(self):
        assert validate_event(_event())["principal"] == "alice"

    def test_unknown_service_rejected(self):
        with pytest.raises(ValidationError):
            validate_event(_event(service="s3"))

    def test_bad_outcome_rejected(self):
        with pytest.raises(ValidationError):
            validate_event(_event(outcome="timeout"))

    def test_missing_principal_rejected(self):
        with pytest.raises(ValidationError):
            validate_event(_event(principal=""))

    def test_negative_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            validate_event(_event(timestamp=-1))

    def test_future_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            validate_event(_event(timestamp=NOW + 3600), now=NOW)

    def test_query_validation(self):
        assert validate_query({"service": "sts", "limit": 10})["limit"] == 10
        with pytest.raises(ValidationError):
            validate_query({"service": "s3"})
        with pytest.raises(ValidationError):
            validate_query({"limit": 0})
        with pytest.raises(ValidationError):
            validate_query({"limit": 501})


class TestIngestAndDedupe:
    def test_ingest_then_duplicate_counts_once(self):
        store = IdentityStore()
        _, dup1 = store.ingest(validate_event(_event()))
        _, dup2 = store.ingest(validate_event(_event()))
        assert dup1 is False
        assert dup2 is True
        assert store.count() == 1

    def test_batch_counts_accepted_duplicates_rejected(self):
        store = IdentityStore()
        summary = store.ingest_batch(
            [
                _event(),
                _event(),  # duplicate
                _event(event_id="evt_002", outcome="denied"),
                _event(event_id="evt_003", service="s3"),  # invalid
            ],
            now=NOW,
        )
        assert summary == {
            "accepted": 2,
            "duplicates": 1,
            "rejected": 1,
            "errors": [{"error": "service must be one of iam, sts, cognito, sso, directory"}],
        }
        assert store.count() == 2

    def test_batch_requires_list(self):
        store = IdentityStore()
        with pytest.raises(ValidationError):
            store.ingest_batch({"event_id": "evt_001"})


class TestFeatures:
    def test_feature_record_aggregates_outcomes(self):
        store = IdentityStore()
        store.ingest_batch(
            [
                _event(event_id="e1", action="AssumeRole"),
                _event(event_id="e2", action="GetSessionToken", service="sts", timestamp=NOW + 60),
                _event(event_id="e3", action="AssumeRole", outcome="denied", timestamp=NOW + 120),
                _event(event_id="e4", action="AssumeRole", outcome="error", timestamp=NOW + 180),
            ],
            now=NOW + 180,
        )
        feats = store.features("alice")
        assert feats["total_events"] == 4
        assert feats["success_events"] == 2
        assert feats["denied_events"] == 1
        assert feats["error_events"] == 1
        assert feats["denial_rate"] == 0.25
        assert feats["high_denial"] is False
        assert feats["distinct_services"] == ["iam", "sts"]
        assert feats["first_seen"] == NOW
        assert feats["last_seen"] == NOW + 180

    def test_high_denial_flagged(self):
        events = [
            _event(event_id=f"e{i}", outcome="denied", timestamp=NOW + i)
            for i in range(3)
        ] + [_event(event_id="e9", timestamp=NOW + 9)]
        feats = build_features("bob", events)
        assert feats["denial_rate"] == 0.75
        assert feats["high_denial"] is True

    def test_unknown_principal_has_no_features(self):
        assert IdentityStore().features("nobody") is None

    def test_query_filters_and_limit(self):
        store = IdentityStore()
        store.ingest_batch(
            [
                _event(event_id="e1", outcome="denied"),
                _event(event_id="e2", outcome="success", service="sts"),
                _event(event_id="e3", outcome="denied", principal="bob"),
            ],
            now=NOW,
        )
        result = store.query({"outcome": "denied"}, limit=1)
        assert result["count"] == 2
        assert result["returned"] == 1
        assert result["events"][0]["event_id"] == "e1"


class TestQualityAndAlerts:
    def test_stale_service_raises_alert_once_then_resolves(self):
        store = IdentityStore()
        store.ingest_batch(
            [
                _event(event_id="e1", service="iam", timestamp=NOW),
                _event(event_id="e2", service="sts", timestamp=NOW + 7200),
            ],
            now=NOW + 7200,
        )
        alerts = store.check_freshness()
        assert len(alerts) == 1
        assert alerts[0]["service"] == "iam"
        assert alerts[0]["type"] == "stale_service"
        # Re-checking raises no second alert for the same service.
        assert len(store.check_freshness()) == 1
        summary = store.quality_summary()
        assert summary["per_service"]["iam"]["stale"] is True
        assert summary["per_service"]["sts"]["stale"] is False
        assert summary["per_service"]["iam"]["lag_seconds"] == 7200
        # A fresh iam event resolves the alert.
        store.ingest(validate_event(_event(event_id="e3", timestamp=NOW + 7200), now=NOW + 7200))
        assert store.active_alerts() == []

    def test_fresh_services_raise_no_alert(self):
        store = IdentityStore()
        store.ingest_batch(
            [
                _event(event_id="e1", service="iam", timestamp=NOW),
                _event(event_id="e2", service="sts", timestamp=NOW + 10),
            ],
            now=NOW + 10,
        )
        assert store.check_freshness() == []

    def test_quality_summary_counts_rejections(self):
        store = IdentityStore()
        store.ingest_batch([_event(), _event(event_id="bad", service="s3")], now=NOW)
        summary = store.quality_summary()
        assert summary["total_events"] == 1
        assert summary["rejected"] == 1
        assert summary["invalid_rate"] == 0.5


class TestHttpFlow:
    def _request(self, server, method, path, body=None):
        port = server.server_address[1]
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_live_identity_flow(self):
        server = create_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, summary = self._request(
                server,
                "POST",
                "/v1/identity/events",
                {"events": [
                    _event(),
                    _event(event_id="evt_002", service="sts", action="GetSessionToken", timestamp=NOW + 60),
                    _event(event_id="evt_003", outcome="denied", timestamp=NOW + 120),
                ]},
            )
            assert status == 201
            assert summary["accepted"] == 3

            status, feats = self._request(server, "GET", "/v1/identity/features/alice")
            assert status == 200
            assert feats["total_events"] == 3
            assert feats["denied_events"] == 1
            assert feats["distinct_services"] == ["iam", "sts"]

            status, result = self._request(
                server, "POST", "/v1/identity/query",
                {"outcome": "denied", "limit": 10},
            )
            assert status == 200
            assert result["count"] == 1

            status, quality = self._request(server, "GET", "/v1/identity/quality")
            assert status == 200
            assert quality["total_events"] == 3
            assert quality["per_service"]["iam"]["stale"] is False

            status, missing = self._request(server, "GET", "/v1/identity/features/nobody")
            assert status == 404
            status, bad = self._request(
                server, "POST", "/v1/identity/events", {"events": "not-a-list"}
            )
            assert status == 400
            status, bad_query = self._request(
                server, "POST", "/v1/identity/query", {"limit": 0}
            )
            assert status == 400
        finally:
            server.shutdown()
            server.server_close()
