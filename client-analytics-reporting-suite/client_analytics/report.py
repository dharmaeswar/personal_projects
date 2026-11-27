"""Stakeholder summary: a short text report for business partners."""


def build(monthly, channels, top, ops, n_valid, n_total, exceptions, mismatches):
    total_volume = sum(r["volume"] for r in monthly)
    total_txns = sum(r["txn_count"] for r in monthly)
    lines = [
        "CLIENT ANALYTICS — STAKEHOLDER SUMMARY (synthetic data, May–Oct 2026)",
        "=" * 74,
        f"Transactions processed: {n_total} ({n_valid} valid, "
        f"{len(exceptions)} exceptions queued for review).",
        f"Total valid volume: ${total_volume:,.2f} across {total_txns} transactions.",
        "",
        "Monthly trend (volume, % change vs prior month):",
    ]
    for r in monthly:
        change = ("n/a" if r["volume_change_pct"] is None
                  else f"{r['volume_change_pct']:+.2f}%")
        lines.append(f"  {r['month']}: ${r['volume']:>12,.2f}  {change:>8}  "
                     f"{r['txn_count']} txns, {r['active_accounts']} active accounts")
    lines.append("")
    lines.append("Volume by channel:")
    for c in channels:
        lines.append(f"  {c['channel']:<8} ${c['volume']:>12,.2f}  "
                     f"{c['txn_count']} txns, avg ticket ${c['avg_ticket']:,.2f}")
    lines.append("")
    lines.append("Top 3 clients by volume:")
    for t in top[:3]:
        lines.append(f"  {t['client_id']} ({t['segment']}): "
                     f"${t['volume']:,.2f} across {t['txn_count']} transactions")
    lines.append("")
    lines.append(f"Operations events: {sum(o['count'] for o in ops)} total; "
                 f"mean resolution "
                 f"{sum(o['count'] * o['avg_resolution_days'] for o in ops) / max(sum(o['count'] for o in ops), 1):.1f} days.")
    lines.append(f"Data quality: {len(exceptions)} exceptions queued; "
                 f"Python/SQL reconciliation mismatches: {len(mismatches)}.")
    lines.append("All figures exclude invalid rows; exceptions are listed in "
                 "dashboards/exceptions.csv for review and escalation.")
    return "\n".join(lines) + "\n"
