#!/usr/bin/env python3
"""CLI runner: health checks, backup verification demo, and DR drill plan."""
import json, sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from dbre.health import check_snapshot, overall_status, SAMPLE_HEALTHY
from dbre.backup import write_backup, verify_backup
from dbre.drill import build_drill_plan, run_drill

def main():
    results=check_snapshot(SAMPLE_HEALTHY)
    for r in results: print(f"{r.status.upper():4} {r.name}: {r.detail} ({r.threshold})")
    print("Overall:", overall_status(results))
    with tempfile.TemporaryDirectory() as td:
        write_backup(td,"demo.dump",b"synthetic-backup-bytes")
        print("Backup verify:", verify_backup(td,"demo.dump"))
    plan=build_drill_plan()
    print(json.dumps(run_drill(plan, results), indent=2))

if __name__=="__main__": main()
