"""Tests for the comms module: templating, preferences, idempotent delivery,
safe retries, confirmed delivery, digesting, delivery monitoring, HTTP API."""

import json
import threading
import urllib.request
import urllib.error

import pytest

from payments_api.app import create_server
from payments_api.comms import (
    CommsService,
    MessageTemplate,
    SimulatedProvider,
    TemplateError,
    UserPreferences,
    build_digest,
)


def _service(fail_times=0):
    return CommsService(SimulatedProvider(fail_times=fail_times))


def _vars(**overrides):
    base = {
        "amount": "$108.31",
        "loan_id": "loan_000001",
        "customer_id": "cust_42",
        "due_date": "2026-12-01",
        "remaining": "$1,191.41",
    }
    base.update(overrides)
    return base


# --- templates ----------------------------------------------------------

def test_template_renders_placeholders():
    rendered = MessageTemplate("t", "email", "Hi {{name}}", "Due {{amount}}").render(
        {"name": "Dharma", "amount": "$10"}
    )
    assert rendered == {"subject": "Hi Dharma", "body": "Due $10"}


def test_template_missing_variable_raises():
    with pytest.raises(TemplateError, match="missing variables: amount"):
        MessageTemplate("t", "email", "Due {{amount}}", "").render({})


def test_template_unknown_channel_raises():
    with pytest.raises(TemplateError, match="unknown channel"):
        MessageTemplate("t", "fax", "", "")


def test_unknown_template_raises():
    with pytest.raises(TemplateError, match="unknown template"):
        _service().send("nope", "cust_42", "a@b.c", {})


# --- preferences ---------------------------------------------------------

def test_preferences_default_is_all_channels():
    assert UserPreferences().channels_for("cust_42") == list(
        ("email", "sms", "push", "slack", "teams", "whatsapp")
    )


def test_preferences_filter_delivery_channels():
    prefs = UserPreferences()
    prefs.set_channels("cust_42", ["email", "push"])
    service = CommsService(SimulatedProvider(), preferences=prefs)
    record = service.send("payment_due", "cust_42", "a@b.c", _vars())
    assert record["channels"] == ["email"]
    assert record["status"] == "delivered"


def test_preferences_unknown_channel_raises():
    with pytest.raises(TemplateError, match="unknown channels"):
        UserPreferences().set_channels("cust_42", ["fax"])


def test_preferences_empty_channels_raises():
    with pytest.raises(TemplateError, match="at least one channel"):
        UserPreferences().set_channels("cust_42", [])


def test_send_with_no_enabled_channel_raises():
    prefs = UserPreferences()
    prefs.set_channels("cust_42", ["push"])
    service = CommsService(SimulatedProvider(), preferences=prefs)
    with pytest.raises(TemplateError, match="none of the requested channels"):
        service.send("payment_due", "cust_42", "a@b.c", _vars(), channels=["email"])


def test_digest_opt_in_roundtrip():
    prefs = UserPreferences()
    assert prefs.digest_enabled("cust_42") is False
    assert prefs.set_digest("cust_42", True) is True
    assert prefs.digest_enabled("cust_42") is True


# --- idempotent delivery --------------------------------------------------

def test_idempotent_send_delivers_once():
    service = _service()
    first = service.send(
        "payment_received", "cust_42", "+17169075982", _vars(),
        idempotency_key="key-1",
    )
    second = service.send(
        "payment_received", "cust_42", "+17169075982", _vars(),
        idempotency_key="key-1",
    )
    assert first["id"] == second["id"]
    assert len(service.provider.delivered) == 1


def test_different_keys_deliver_twice():
    service = _service()
    service.send("payment_received", "cust_42", "+1", _vars(), idempotency_key="k1")
    service.send("payment_received", "cust_42", "+1", _vars(), idempotency_key="k2")
    assert len(service.provider.delivered) == 2


# --- retries and confirmed delivery ---------------------------------------

def test_transient_provider_failure_retries_then_confirms():
    service = _service(fail_times=2)
    record = service.send("payment_received", "cust_42", "+1", _vars())
    assert record["status"] == "delivered"
    assert record["deliveries"][0]["provider_message_id"] is not None
    assert service.provider.calls == 3  # 2 failures + 1 success


def test_persistent_provider_failure_marks_failed_not_lost():
    service = _service(fail_times=99)
    record = service.send("payment_received", "cust_42", "+1", _vars())
    assert record["status"] == "failed"
    assert record["deliveries"][0]["provider_message_id"] is None
    assert service.get(record["id"])["status"] == "failed"


def test_multi_channel_send_reports_partial_on_one_failure():
    inner = SimulatedProvider()

    class FlakyProvider:
        def send(self, channel, recipient, subject, body):
            if channel == "sms":
                raise RuntimeError("sms provider down")
            return inner.send(channel, recipient, subject, body)

    service = CommsService(FlakyProvider())
    record = service.send(
        "payment_due", "cust_42", "a@b.c", _vars(), channels=["email", "sms"]
    )
    assert record["status"] == "partial"
    by_channel = {d["channel"]: d["status"] for d in record["deliveries"]}
    assert by_channel == {"email": "delivered", "sms": "failed"}


# --- delivery monitoring ---------------------------------------------------

def test_delivery_summary_counts_and_rate():
    service = _service(fail_times=99)
    service.send("payment_received", "cust_42", "+1", _vars())
    service2 = _service()
    service2.send("payment_received", "cust_42", "+1", _vars())
    summary = service2.delivery_summary()
    assert summary["total_attempts"] == 1
    assert summary["delivered"] == 1
    assert summary["delivery_rate"] == 1.0
    assert summary["per_channel"]["sms"]["delivered"] == 1
    assert service.delivery_summary()["failed"] == 1


def test_delivery_summary_empty_is_healthy():
    assert _service().delivery_summary()["delivery_rate"] == 1.0


# --- digesting --------------------------------------------------------------

def test_build_digest_groups_messages():
    digest = build_digest(
        "cust_42",
        "email",
        [
            {"subject": "Payment due", "body": "$108.31 due Dec 1"},
            {"subject": "", "body": "Payment received"},
        ],
    )
    assert digest["message_count"] == 2
    assert digest["subject"] == "Your digest: 2 updates"
    assert "Payment due: $108.31 due Dec 1" in digest["body"]


def test_build_digest_empty_raises():
    with pytest.raises(TemplateError, match="no messages"):
        build_digest("cust_42", "email", [])


# --- HTTP API ---------------------------------------------------------------

def _post(url, payload, key=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **({"Idempotency-Key": key} if key else {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _get(url):
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_http_comms_flow():
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        status, record = _post(
            f"{base}/v1/comms/messages",
            {
                "template": "payment_due",
                "user_id": "cust_42",
                "recipient": "a@b.c",
                "variables": _vars(),
            },
            key="http-1",
        )
        assert status == 201
        assert record["status"] == "delivered"
        status, again = _post(
            f"{base}/v1/comms/messages",
            {
                "template": "payment_due",
                "user_id": "cust_42",
                "recipient": "a@b.c",
                "variables": _vars(),
            },
            key="http-1",
        )
        assert again["id"] == record["id"]  # idempotent retry
        status, fetched = _get(f"{base}/v1/comms/messages/{record['id']}")
        assert status == 200 and fetched["id"] == record["id"]
        status, summary = _get(f"{base}/v1/comms/delivery")
        assert status == 200 and summary["delivered"] == 1
        status, prefs = _post(
            f"{base}/v1/comms/preferences/cust_42",
            {"channels": ["email", "sms"], "digest": True},
        )
        assert status == 200 and prefs["channels"] == ["email", "sms"]
        assert prefs["digest"] is True
        status, prefs = _get(f"{base}/v1/comms/preferences/cust_42")
        assert status == 200 and prefs["channels"] == ["email", "sms"]
        status, digest = _post(
            f"{base}/v1/comms/digest",
            {
                "user_id": "cust_42",
                "channel": "email",
                "messages": [{"subject": "A", "body": "one"}, {"subject": "", "body": "two"}],
            },
        )
        assert status == 200 and digest["message_count"] == 2
        status, err = _post(
            f"{base}/v1/comms/messages",
            {"template": "payment_due", "user_id": "cust_42", "recipient": "a@b.c", "variables": {}},
        )
        assert status == 400 and "missing variables" in err["error"]
        status, err = _get(f"{base}/v1/comms/messages/msg_999999")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
