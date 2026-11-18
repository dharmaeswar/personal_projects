"""Pipeline runner: ingest -> validate -> balance -> detect -> report.

Reads a JSON feed of journal-entry lines, stages them in SQLite, runs the
balance and anomaly checks, and writes the close-ready outputs:
trial_balance.csv, anomaly_report.json and close_report.json.
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import anomaly, ledger
from src.contracts import CHART_OF_ACCOUNTS, validate_line


def load_feed(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return data["journal_lines"]
    return data


def run(feed_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "ledger.db"
    if db_path.exists():
        db_path.unlink()  # a run rebuilds from the feed: re-runs never double-count

    lines = load_feed(feed_path)
    conn = ledger.open_db(db_path)

    valid, quarantined = [], 0
    seen_entry_ids = set()
    for line in lines:
        errors = validate_line(line)
        if line.get("entry_id") in seen_entry_ids:
            errors = errors + ["duplicate entry_id"]
        if errors:
            ledger.quarantine_line(conn, line, "; ".join(errors))
            quarantined += 1
        else:
            seen_entry_ids.add(line["entry_id"])
            valid.append(line)
    ledger.insert_lines(conn, valid)

    unbalanced = ledger.check_journal_balances(conn)
    duplicates = ledger.find_duplicates(conn)
    clean_ids = ledger.clean_entry_ids(conn)

    clean_lines = []
    if clean_ids:
        cursor = conn.execute(
            "SELECT * FROM raw_lines WHERE entry_id IN (%s)" % ",".join("?" for _ in clean_ids),
            clean_ids,
        )
        columns = [d[0] for d in cursor.description]
        clean_lines = [dict(zip(columns, row)) for row in cursor.fetchall()]

    flags = anomaly.run_all_checks(clean_lines)
    for entry_id, details in flags.items():
        for detail in details:
            conn.execute(
                "INSERT OR REPLACE INTO line_flags VALUES (?,?,?)",
                (entry_id, detail.split(":")[0], detail),
            )
    conn.commit()

    tb = ledger.trial_balance(conn, clean_ids)
    total_debit = round(sum(row["debit"] for row in tb), 2)
    total_credit = round(sum(row["credit"] for row in tb), 2)
    benford, benford_max_dev = anomaly.benford_check(clean_lines)

    with open(output_dir / "trial_balance.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["account", "account_name", "debit", "credit", "net"])
        for row in tb:
            writer.writerow(
                [row["account"], CHART_OF_ACCOUNTS[row["account"]], f"{row['debit']:.2f}",
                 f"{row['credit']:.2f}", f"{row['net']:.2f}"]
            )
        writer.writerow(["TOTAL", "", f"{total_debit:.2f}", f"{total_credit:.2f}",
                         f"{round(total_debit - total_credit, 2):.2f}"])

    anomaly_report = {
        "flagged_lines": len(flags),
        "flags": {entry_id: details for entry_id, details in sorted(flags.items())},
    }
    with open(output_dir / "anomaly_report.json", "w", encoding="utf-8") as handle:
        json.dump(anomaly_report, handle, indent=2)

    close_report = {
        "feed_lines": len(lines),
        "valid_lines": len(valid),
        "quarantined_lines": quarantined,
        "unbalanced_journals": [
            {"journal_id": j, "total_debit": d, "total_credit": c} for j, d, c in unbalanced
        ],
        "duplicate_lines": duplicates,
        "clean_lines_in_trial_balance": len(clean_ids),
        "trial_balance_total_debit": total_debit,
        "trial_balance_total_credit": total_credit,
        "books_balanced": total_debit == total_credit,
        "benford_first_digit": {str(k): v for k, v in benford.items()},
        "benford_max_deviation": benford_max_dev,
        "flagged_lines": len(flags),
    }
    with open(output_dir / "close_report.json", "w", encoding="utf-8") as handle:
        json.dump(close_report, handle, indent=2)

    conn.close()
    return close_report


if __name__ == "__main__":
    feed = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "data" / "sample_journals.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "output"
    report = run(feed, out)
    print(json.dumps(report, indent=2))
