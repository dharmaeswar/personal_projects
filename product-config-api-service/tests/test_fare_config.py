"""Tests for the fare-configuration example.

A fare configuration is a product config whose modules are fare rules:
base fare, per-mile / per-minute rates, a surge multiplier, and the
service area. The tests exercise the same publish workflow a fares
platform needs: validate a fare change, publish it, serve only the
published version, and roll back by republishing the previous version.
All fare values here are synthetic examples.
"""

import copy
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from product_config.ai_assist import completeness_score, suggest_defaults  # noqa: E402
from product_config.api import _dispatch  # noqa: E402
from product_config.models import ProductConfig  # noqa: E402
from product_config.service import ConfigService, ValidationError  # noqa: E402
from product_config.store import ConfigStore  # noqa: E402

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def fare_data(**overrides):
    with open(os.path.join(EXAMPLES, "fare_config.json")) as f:
        data = json.load(f)
    data.update(overrides)
    return data


@pytest.fixture()
def service():
    with tempfile.TemporaryDirectory() as tmp:
        yield ConfigService(ConfigStore(os.path.join(tmp, "configs.json")))


def test_example_fare_config_is_valid():
    assert ProductConfig.from_dict(fare_data()).validate() == []


def test_fare_config_publishes_and_is_served(service):
    service.create(fare_data())
    published = service.publish("city-fare-us", 1)
    assert published.status == "published"
    served = service.get_published("city-fare-us")
    assert served.version == 1
    modules = {m.name for m in served.modules}
    assert modules == {"base-fare", "distance-rate", "time-rate", "surge", "service-area"}


def test_fare_update_creates_new_version_and_rollback_keeps_v1(service):
    service.create(fare_data())
    service.publish("city-fare-us", 1)
    v2 = copy.deepcopy(fare_data())
    v2["modules"][0]["attributes"][0]["value"] = 2.75
    created = service.create_next_version("city-fare-us", v2)
    assert created.version == 2
    assert created.status == "draft"
    service.publish("city-fare-us", 2)
    assert service.get_published("city-fare-us").version == 2
    assert service.get("city-fare-us", 1).status == "published"
    assert service.get("city-fare-us", 1).modules[0].attributes[0].value == 2.5


def test_invalid_surge_multiplier_is_rejected(service):
    data = fare_data()
    data["modules"][3]["attributes"][0]["value"] = 9.9
    with pytest.raises(ValidationError, match="not in"):
        service.create(data)


def test_duplicate_fare_module_is_rejected(service):
    data = fare_data()
    data["modules"].append(copy.deepcopy(data["modules"][0]))
    with pytest.raises(ValidationError, match="duplicate module"):
        service.create(data)


def test_fare_config_cannot_skip_review(service):
    service.create(fare_data())
    with pytest.raises(ValidationError, match="cannot move"):
        service.transition("city-fare-us", 1, "published")


def test_fare_config_completeness_and_default_suggestion():
    config = ProductConfig.from_dict(fare_data())
    assert completeness_score(config) == 1.0
    suggestions = suggest_defaults(config)
    assert suggestions["pricing.currency"]["value"] == "USD"


def test_fare_config_http_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_STORE_PATH", str(tmp_path / "configs.json"))
    status, _ = _dispatch("POST", "/v1/products", {},
                          json.dumps(fare_data()).encode())
    assert status == 201
    status, body = _dispatch("POST", "/v1/products/city-fare-us/publish",
                             {"version": ["1"]}, b"")
    assert status == 200
    assert body["status"] == "published"
    status, body = _dispatch("GET", "/v1/products/city-fare-us/published", {}, b"")
    assert status == 200
    assert body["modules"][0]["attributes"][0]["value"] == 2.5
