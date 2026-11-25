"""CLI entry point: run the marketplace-intelligence pipeline on the
seeded data and write market_report.json + CATALOG.md next to this file.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from marketintel.pipeline import run_pipeline  # noqa: E402

BASE = Path(__file__).resolve().parent


def main():
    db_path = BASE / "marketplace.sqlite"
    report = run_pipeline(BASE / "data", str(db_path))
    (BASE / "market_report.json").write_text(json.dumps(report, indent=2))
    catalog = report.get("catalog", "")
    (BASE / "CATALOG.md").write_text(catalog)
    print(json.dumps({k: v for k, v in report.items() if k != "catalog"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
