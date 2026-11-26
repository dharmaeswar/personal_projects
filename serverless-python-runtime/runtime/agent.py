"""Worker agent process: the long-lived process that runs one handler.

The executor spawns one agent per worker. The agent reads JSON-lines
requests on stdin, imports the handler module on first use (that import is
the cold start), reuses the loaded module for later invocations (warm), and
writes one JSON-lines response per request with import time, execution time,
and either the result or the error. Keeping the agent separate from the
executor means a crashing handler cannot take the runtime down with it.
"""

import importlib.util
import json
import sys
import time
import traceback


def main() -> None:
    loaded: dict[tuple[str, str], object] = {}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        started = time.perf_counter()
        key = (request["handler_path"], request["function"])
        cold = key not in loaded
        import_ms = 0.0
        try:
            if cold:
                spec = importlib.util.spec_from_file_location(
                    "user_handler", request["handler_path"]
                )
                if spec is None or spec.loader is None:
                    raise ImportError(
                        f"cannot load handler {request['handler_path']!r}"
                    )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                loaded[key] = getattr(module, request["function"])
                import_ms = (time.perf_counter() - started) * 1000
            call_started = time.perf_counter()
            result = loaded[key](request.get("event") or {})
            exec_ms = (time.perf_counter() - call_started) * 1000
            response = {
                "ok": True,
                "result": result,
                "cold": cold,
                "import_ms": round(import_ms, 3),
                "exec_ms": round(exec_ms, 3),
                "total_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        except Exception as exc:  # noqa: BLE001 - report handler errors, don't crash
            response = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "cold": cold,
                "import_ms": round(import_ms, 3),
                "total_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
