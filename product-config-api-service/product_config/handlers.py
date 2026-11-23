"""Lambda-style handlers.

Each handler takes an API Gateway-style event dict and returns a
(statusCode, body) pair, so the same code runs behind API Gateway in AWS
or behind the local stdlib HTTP server in api.py. No AWS SDK is needed
locally; the store path is passed in through the environment.
"""

from __future__ import annotations

import json
import os

from .service import ConfigService, ValidationError
from .store import ConfigStore


def _service() -> ConfigService:
    path = os.environ.get("CONFIG_STORE_PATH", "configs.json")
    return ConfigService(ConfigStore(path))


def _response(status: int, body: dict) -> dict:
    return {"statusCode": status, "body": json.dumps(body)}


def create_config(event: dict, _context=None) -> dict:
    try:
        data = json.loads(event.get("body") or "{}")
        config = _service().create(data)
    except ValidationError as exc:
        return _response(400, {"error": str(exc)})
    except (KeyError, TypeError, ValueError) as exc:
        return _response(400, {"error": f"invalid payload: {exc}"})
    return _response(201, config.to_dict())


def get_config(event: dict, _context=None) -> dict:
    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    try:
        version = int(query["version"]) if query.get("version") else None
        config = _service().get(params["product_id"], version)
    except KeyError:
        return _response(404, {"error": "product not found"})
    except ValueError:
        return _response(400, {"error": "version must be an integer"})
    return _response(200, config.to_dict())


def get_published_config(event: dict, _context=None) -> dict:
    params = event.get("pathParameters") or {}
    try:
        config = _service().get_published(params["product_id"])
    except KeyError:
        return _response(404, {"error": "no published config for product"})
    return _response(200, config.to_dict())


def publish_config(event: dict, _context=None) -> dict:
    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    try:
        version = int(query.get("version", "1"))
        config = _service().publish(params["product_id"], version)
    except KeyError:
        return _response(404, {"error": "product not found"})
    except ValidationError as exc:
        return _response(422, {"error": str(exc)})
    return _response(200, config.to_dict())


def suggest_config(event: dict, _context=None) -> dict:
    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    try:
        version = int(query.get("version", "1"))
        service = _service()
        config = service.get(params["product_id"], version)
        from .ai_assist import check_conflicts, completeness_score

        body = {
            "suggestions": service.defaults_for(params["product_id"], version),
            "warnings": check_conflicts(config),
            "completeness": completeness_score(config),
        }
    except KeyError:
        return _response(404, {"error": "product not found"})
    return _response(200, body)
