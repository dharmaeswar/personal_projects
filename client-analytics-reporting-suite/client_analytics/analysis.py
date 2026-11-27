"""KPI analysis: monthly and channel aggregates, trends, top clients."""

from collections import defaultdict


def kpi_by_month(valid):
    """Per month: txn count, total volume, average ticket, active accounts."""
    agg = {}
    for d in valid:
        m = agg.setdefault(d["month"], {"txn_count": 0, "volume": 0.0, "accounts": set()})
        m["txn_count"] += 1
        m["volume"] += d["amount"]
        m["accounts"].add(d["account_id"])
    out = []
    for month in sorted(agg):
        m = agg[month]
        out.append({"month": month, "txn_count": m["txn_count"],
                    "volume": round(m["volume"], 2),
                    "avg_ticket": round(m["volume"] / m["txn_count"], 2),
                    "active_accounts": len(m["accounts"])})
    return out


def kpi_by_channel(valid):
    agg = {}
    for d in valid:
        c = agg.setdefault(d["channel"], {"txn_count": 0, "volume": 0.0})
        c["txn_count"] += 1
        c["volume"] += d["amount"]
    out = []
    for channel in sorted(agg):
        c = agg[channel]
        out.append({"channel": channel, "txn_count": c["txn_count"],
                    "volume": round(c["volume"], 2),
                    "avg_ticket": round(c["volume"] / c["txn_count"], 2)})
    return out


def month_over_month(kpis):
    """Add volume change vs the previous month (percent, None for first)."""
    out = []
    prev = None
    for row in kpis:
        r = dict(row)
        r["volume_change_pct"] = (None if prev is None
                                  else round((r["volume"] - prev) / prev * 100, 2))
        out.append(r)
        prev = r["volume"]
    return out


def top_clients(conn, valid, limit=10):
    """Top clients by valid transaction volume, joined to segment."""
    totals = defaultdict(float)
    counts = defaultdict(int)
    account_client = {r["account_id"]: r["client_id"]
                      for r in conn.execute("SELECT account_id, client_id FROM accounts")}
    for d in valid:
        client = account_client[d["account_id"]]
        totals[client] += d["amount"]
        counts[client] += 1
    segments = {r["client_id"]: r["segment"]
                for r in conn.execute("SELECT client_id, segment FROM clients")}
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [{"client_id": cid, "segment": segments.get(cid, "UNKNOWN"),
             "txn_count": counts[cid], "volume": round(total, 2)}
            for cid, total in ranked]


def ops_summary(conn):
    """Operations events: count and mean resolution days by type and month."""
    rows = conn.execute(
        "SELECT month, event_type, COUNT(*) AS n, AVG(resolution_days) AS avg_days"
        " FROM ops_events GROUP BY month, event_type ORDER BY month, event_type").fetchall()
    return [{"month": r["month"], "event_type": r["event_type"], "count": r["n"],
             "avg_resolution_days": round(r["avg_days"], 2)} for r in rows]
