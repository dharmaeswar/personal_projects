"""Dashboard outputs: CSV files (open in Excel) and a plain HTML dashboard."""

import csv
import html
import os


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def _table(title, rows, fields):
    parts = [f"<h2>{html.escape(title)}</h2>", "<table><tr>"]
    parts += [f"<th>{html.escape(f)}</th>" for f in fields]
    parts.append("</tr>")
    for row in rows:
        parts.append("<tr>" + "".join(
            f"<td>{html.escape(str(row.get(f, '')))}</td>" for f in fields) + "</tr>")
    parts.append("</table>")
    return "\n".join(parts)


def write_html_dashboard(path, monthly, channels, top, ops, exceptions, mismatches):
    body = ["<html><head><meta charset='utf-8'>",
            "<title>Client Analytics Dashboard</title>",
            "<style>body{font-family:sans-serif;margin:24px}"
            "table{border-collapse:collapse;margin-bottom:20px}"
            "th,td{border:1px solid #999;padding:4px 10px;text-align:left}"
            "th{background:#eee}</style></head><body>",
            "<h1>Client Analytics Dashboard — May–Oct 2026 (synthetic data)</h1>",
            "<p>All figures are computed from valid transactions only; "
            "invalid rows are listed under Exceptions and excluded from KPIs.</p>"]
    body.append(_table("Monthly KPIs", monthly,
                       ["month", "txn_count", "volume", "avg_ticket",
                        "active_accounts", "volume_change_pct"]))
    body.append(_table("KPIs by Channel", channels,
                       ["channel", "txn_count", "volume", "avg_ticket"]))
    body.append(_table("Top 10 Clients by Volume", top,
                       ["client_id", "segment", "txn_count", "volume"]))
    body.append(_table("Operations Events", ops,
                       ["month", "event_type", "count", "avg_resolution_days"]))
    body.append(_table("Exceptions (excluded from KPIs)", exceptions,
                       ["txn_id", "check", "detail"]))
    body.append(f"<p>Python/SQL reconciliation mismatches: {len(mismatches)}</p>")
    body.append("</body></html>")
    with open(path, "w") as f:
        f.write("\n".join(body))


def build(out_dir, monthly, channels, top, ops, exceptions, mismatches):
    os.makedirs(out_dir, exist_ok=True)
    write_csv(os.path.join(out_dir, "kpi_by_month.csv"), monthly,
              ["month", "txn_count", "volume", "avg_ticket", "active_accounts",
               "volume_change_pct"])
    write_csv(os.path.join(out_dir, "kpi_by_channel.csv"), channels,
              ["channel", "txn_count", "volume", "avg_ticket"])
    write_csv(os.path.join(out_dir, "top_clients.csv"), top,
              ["client_id", "segment", "txn_count", "volume"])
    write_csv(os.path.join(out_dir, "ops_summary.csv"), ops,
              ["month", "event_type", "count", "avg_resolution_days"])
    write_csv(os.path.join(out_dir, "exceptions.csv"), exceptions,
              ["txn_id", "check", "detail"])
    write_html_dashboard(os.path.join(out_dir, "dashboard.html"),
                         monthly, channels, top, ops, exceptions, mismatches)
    return sorted(os.listdir(out_dir))
