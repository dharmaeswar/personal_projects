"""Tests for models, store, service, handlers, and the HTTP API."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from product_config import handlers  # noqa: E402
from product_config.ai_assist import check_conflicts, completeness_score, suggest_defaults  # noqa: E402
from product_config.api import _dispatch  # noqa: E402
from product_config.models import ProductConfig  # noqa: E402
from product_config.service import ConfigService, ValidationError  # noqa: E402
from product_config.store import ConfigStore  # noqa: E402


def sample_data(**overrides):
    data = {
        "product_id": "runner-x1",
        "name": "Runner X1",
        "version": 1,
        "status": "draft",
        "modules": [
            {
                "name": "materials",
                "attributes": [
                    {"name": "upper-material", "type": "enum",
                     "value": "engineered-mesh",
                     "options": ["engineered-mesh", "suede", "leather"],
                     "required": True},
                ],
            },
            {
                "name": "sizing",
                "attributes": [
                    {"name": "size-run", "type": "enum", "value": "US 7",
                     "options": ["US 7", "US 8", "US 9"], "required": True},
                ],
            },
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture()
def service():
    with tempfile.TemporaryDirectory() as tmp:
        yield ConfigService(ConfigStore(os.path.join(tmp, "configs.json")))


# --- models ---

def test_valid_config_passes_validation():
    assert ProductConfig.from_dict(sample_data()).validate() == []


def test_enum_value_outside_options_is_rejected():
    data = sample_data()
    data["modules"][0]["attributes"][0]["value"] = "canvas"
    errors = ProductConfig.from_dict(data).validate()
    assert any("not in" in e for e in errors)


def test_bad_product_id_is_rejected():
    assert ProductConfig.from_dict(sample_data(product_id="Runner X1")).validate()


def test_config_without_modules_is_rejected():
    assert ProductConfig.from_dict(sample_data(modules=[])).validate()


def test_duplicate_attribute_is_rejected():
    data = sample_data()
    data["modules"][0]["attributes"].append(
        {"name": "upper-material", "type": "string", "value": "mesh"})
    assert ProductConfig.from_dict(data).validate()


def test_roundtrip_through_dict():
    config = ProductConfig.from_dict(sample_data())
    assert ProductConfig.from_dict(config.to_dict()).to_dict() == config.to_dict()


# --- store ---

def test_store_put_get_latest_and_published(service):
    store = service.store
    cfg = ProductConfig.from_dict(sample_data())
    store.put(cfg)
    assert store.get("runner-x1", 1).name == "Runner X1"
    assert store.latest("runner-x1").version == 1
    assert store.latest_published("runner-x1") is None
    cfg.status = "published"
    store.update(cfg)
    assert store.latest_published("runner-x1").version == 1
    assert store.get("missing", 1) is None


def test_store_rejects_duplicate_version(service):
    store = service.store
    store.put(ProductConfig.from_dict(sample_data()))
    with pytest.raises(ValueError, match="already exists"):
        store.put(ProductConfig.from_dict(sample_data()))


def test_store_persists_across_reopen():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "configs.json")
        ConfigStore(path).put(ProductConfig.from_dict(sample_data()))
        assert ConfigStore(path).latest("runner-x1").name == "Runner X1"


# --- service ---

def test_create_and_get(service):
    created = service.create(sample_data())
    assert created.status == "draft"
    assert service.get("runner-x1").product_id == "runner-x1"


def test_create_rejects_invalid_config(service):
    with pytest.raises(ValidationError):
        service.create(sample_data(modules=[]))


def test_get_missing_product_raises(service):
    with pytest.raises(KeyError):
        service.get("nope")


def test_publish_workflow_moves_draft_to_published(service):
    service.create(sample_data())
    published = service.publish("runner-x1", 1)
    assert published.status == "published"
    assert service.get_published("runner-x1").version == 1


def test_illegal_transition_is_rejected(service):
    service.create(sample_data())
    with pytest.raises(ValidationError, match="cannot move"):
        service.transition("runner-x1", 1, "published")


def test_create_next_version_bumps_and_resets_status(service):
    service.create(sample_data())
    service.publish("runner-x1", 1)
    v2 = service.create_next_version("runner-x1", sample_data())
    assert v2.version == 2
    assert v2.status == "draft"


def test_get_published_with_no_published_config_raises(service):
    service.create(sample_data())
    with pytest.raises(KeyError):
        service.get_published("runner-x1")


# --- ai assist ---

def test_suggest_defaults_fills_missing_attributes():
    config = ProductConfig.from_dict(sample_data())
    suggestions = suggest_defaults(config)
    assert "pricing.currency" in suggestions
    assert suggestions["pricing.currency"]["value"] == "USD"
    assert "materials.upper-material" not in suggestions


def test_conflict_warning_for_suede_white():
    data = sample_data()
    data["modules"][0]["attributes"][0]["value"] = "suede"
    data["modules"].append({
        "name": "colourways",
        "attributes": [{"name": "primary-colour", "type": "string", "value": "white"}],
    })
    assert check_conflicts(ProductConfig.from_dict(data))


def test_completeness_score_counts_required_attributes():
    config = ProductConfig.from_dict(sample_data())
    assert completeness_score(config) == 1.0
    config.modules[0].attributes[0].value = ""
    assert completeness_score(config) == 0.5


# --- handlers ---

@pytest.fixture()
def _store_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_STORE_PATH", str(tmp_path / "configs.json"))


def test_handler_create_and_get_roundtrip(_store_env):
    created = handlers.create_config({"body": json.dumps(sample_data())})
    assert created["statusCode"] == 201
    got = handlers.get_config({"pathParameters": {"product_id": "runner-x1"},
                               "queryStringParameters": {}})
    assert got["statusCode"] == 200
    assert json.loads(got["body"])["name"] == "Runner X1"


def test_handler_create_invalid_returns_400(_store_env):
    result = handlers.create_config({"body": json.dumps(sample_data(modules=[]))})
    assert result["statusCode"] == 400


def test_handler_get_missing_returns_404(_store_env):
    result = handlers.get_config({"pathParameters": {"product_id": "nope"},
                                  "queryStringParameters": {}})
    assert result["statusCode"] == 404


def test_handler_publish_flow(_store_env):
    handlers.create_config({"body": json.dumps(sample_data())})
    result = handlers.publish_config(
        {"pathParameters": {"product_id": "runner-x1"},
         "queryStringParameters": {"version": "1"}})
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["status"] == "published"


def test_handler_suggest_returns_score_and_suggestions(_store_env):
    handlers.create_config({"body": json.dumps(sample_data())})
    result = handlers.suggest_config(
        {"pathParameters": {"product_id": "runner-x1"},
         "queryStringParameters": {"version": "1"}})
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["completeness"] == 1.0
    assert "pricing.currency" in body["suggestions"]


# --- HTTP dispatch ---

def test_dispatch_health_and_unknown_routes():
    assert _dispatch("GET", "/health", {}, b"") == (200, {"status": "ok"})
    status, _ = _dispatch("GET", "/nope", {}, b"")
    assert status == 404


def test_dispatch_create_and_read_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_STORE_PATH", str(tmp_path / "configs.json"))
    status, body = _dispatch("POST", "/v1/products", {},
                             json.dumps(sample_data()).encode())
    assert status == 201
    status, body = _dispatch("GET", "/v1/products/runner-x1", {}, b"")
    assert status == 200
    assert body["product_id"] == "runner-x1"
    status, body = _dispatch("POST", "/v1/products/runner-x1/publish?x=1", {}, b"")
    assert status in (200, 404)  # query parsing is exercised below instead
    status, body = _dispatch("POST", "/v1/products/runner-x1/publish",
                             {"version": ["1"]}, b"")
    assert status == 200
    assert body["status"] == "published"
