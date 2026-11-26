"""Run the ADF-style daily pipeline through the DAG runner."""
import json

from claims_platform.orchestration import load_pipeline, run_pipeline
from claims_platform.pipeline import run as run_claims


def execute(name):
    if name == "IngestRawClaims":
        run_claims()  # ingest + bronze + silver + gold in one local run
    elif name in ("ValidateSilver", "PublishGold", "RefreshApiCache"):
        return  # validated inside run_claims; API reads the written layers
    else:
        raise ValueError(f"unknown activity: {name}")


if __name__ == "__main__":
    pipeline = load_pipeline()
    log = run_pipeline(pipeline, execute)
    print(json.dumps(log, indent=2))
