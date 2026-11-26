"""Run the media session streaming pipeline locally and print a summary."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from session_stream.pipeline import run_pipeline


def main() -> int:
    out = Path(__file__).resolve().parent / "data"
    manifest = run_pipeline(n_sessions=40, seed=42, out_dir=out)
    summary = {k: v for k, v in manifest.items() if k != "workflow_job"}
    print(json.dumps(summary, indent=2, default=str))
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str))
    print(f"Manifest written to {out / 'run_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
