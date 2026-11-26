"""Example handler: a tiny greeting function with a fake dependency import.

The import of `json` plus a module-level lookup stands in for the heavier
imports real handlers carry (frameworks, SDKs). Its cold start is the import
time the runtime measures; warm invocations skip it.
"""

import json

_GREETING = json.loads('{"hello": "world"}')


def handle(event):
    """Return a greeting for the name in the event, plus the loaded config."""
    name = event.get("name", "developer")
    return {"message": f"Hello, {name}!", "config": _GREETING, "n": event.get("n", 0)}


def boom(event):
    """A handler that always fails, so error reporting can be exercised."""
    raise ValueError("boom on purpose")
