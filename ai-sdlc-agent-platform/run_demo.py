"""CLI entry point: run the AI SDLC agent platform on the seeded repo and
write sdlc_report.json + DASHBOARD.md next to this file."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sdlc_agents import observability  # noqa: E402
from sdlc_agents.pipeline import run_pipeline  # noqa: E402

BASE = Path(__file__).resolve().parent


def main() -> int:
    db_path = BASE / "sdlc.sqlite"
    if db_path.exists():
        db_path.unlink()
    report = run_pipeline(BASE / "data" / "seed_repo.json", db_path)
    (BASE / "sdlc_report.json").write_text(json.dumps(report, indent=2))
    conn = observability.init_db(str(db_path))
    (BASE / "DASHBOARD.md").write_text(observability.dashboard_markdown(conn))
    conn.close()
    print(json.dumps({k: v for k, v in report.items() if k != "dashboard"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
