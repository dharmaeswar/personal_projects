"""End-to-end demo: package the example handler, invoke it cold then warm.

Run:  python run_demo.py
Shows: bundle size and precompilation, one cold invocation (import time
counted), three warm invocations (import time zero), and the metrics summary.
"""

import json
import tempfile
from pathlib import Path

from runtime.executor import Executor
from runtime.config import RuntimeConfig
from runtime.packaging import build_bundle

ROOT = Path(__file__).parent


def main() -> None:
    handler = ROOT / "examples" / "handler.py"
    requirements = "requests==2.32.3\npydantic>=2.7.0\n"
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        manifest = build_bundle(handler, requirements, bundle, size_budget_mb=250)
        print("Bundle:", json.dumps(manifest, indent=2))

    config = RuntimeConfig(memory_mb=512, timeout_s=30, max_concurrency=5)
    with Executor(config) as executor:
        for i, name in enumerate(["Ada", "Grace", "Linus", "Margaret"]):
            response = executor.invoke(
                str(handler), "handle", {"name": name, "n": i}
            )
            print(
                f"invoke {i + 1}: cold={response['cold']} "
                f"import_ms={response['import_ms']} "
                f"exec_ms={response['exec_ms']} "
                f"result={response['result']}"
            )
        print("Metrics:", json.dumps(executor.metrics.summary(), indent=2))


if __name__ == "__main__":
    main()
