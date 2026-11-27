"""Shared fixtures: small synthetic event sets. No real user data."""
from datetime import datetime

import pytest

from signals.models import Consent

NOW = datetime(2026, 11, 26, 12, 0, 0)


def raw_event(event_id="evt-1", user_id="user-01", event_type="product_usage",
              ts="2026-11-26T10:00:00", payload=None):
    return {"event_id": event_id, "user_id": user_id, "event_type": event_type,
            "source": "copilot-app", "timestamp": ts,
            "payload": payload or {"workflow": "draft-email", "feature": "draft",
                                   "goal": "writing", "duration_seconds": 120}}


@pytest.fixture
def consent():
    return Consent(user_id="user-01")
