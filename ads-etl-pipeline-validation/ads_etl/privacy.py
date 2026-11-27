"""Privacy-safe reporting gate for advertising aggregates.

T-Ads is privacy-first advertising: a published aggregate must never rest
on a handful of events, because a tiny cell can leak information about a
single advertiser or audience. This module enforces a minimum-cell-size
rule on a campaign/channel rollup built from silver: any group fed by
fewer than ``min_source_rows`` silver events is suppressed from the
published rollup and listed separately, with its spend held out of the
published total. Nothing is dropped silently — suppressed groups are
counted and reported, and published + suppressed spend always reconciles
back to the silver total.

The rollup is built from silver rows in plain Python (no extra engine);
it is a reporting gate, not a second gold table.
"""

from __future__ import annotations

DEFAULT_MIN_SOURCE_ROWS = 5


def build_privacy_safe_rollup(
    silver: list[dict],
    channel_of: dict[str, str] | None = None,
    min_source_rows: int = DEFAULT_MIN_SOURCE_ROWS,
) -> dict:
    """Build a privacy-safe campaign/channel rollup from silver rows.

    Groups silver events by (channel, campaign_id). A group with fewer
    than ``min_source_rows`` source events is suppressed: it stays out of
    the published rollup and is listed in ``suppressed`` with its spend,
    so the gate is auditable. Returns a dict with ``published``,
    ``suppressed`` and ``summary`` keys.

    ``channel_of`` maps campaign_id -> channel; when it is not given the
    channel is reported as "unknown".
    """
    if min_source_rows < 1:
        raise ValueError("min_source_rows must be at least 1")

    channel_of = channel_of or {}
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in silver:
        key = (channel_of.get(row["campaign_id"], "unknown"), row["campaign_id"])
        grouped.setdefault(key, []).append(row)

    published: list[dict] = []
    suppressed: list[dict] = []
    for (channel, campaign_id), rows in sorted(grouped.items()):
        entry = {
            "channel": channel,
            "campaign_id": campaign_id,
            "source_row_count": len(rows),
            "impressions": sum(r["impressions"] for r in rows),
            "clicks": sum(r["clicks"] for r in rows),
            "spend_usd": round(sum(r["spend_usd"] for r in rows), 2),
        }
        if len(rows) < min_source_rows:
            entry["suppression_reason"] = (
                f"fewer than {min_source_rows} source events "
                f"({len(rows)} found)"
            )
            suppressed.append(entry)
        else:
            published.append(entry)

    silver_spend = round(sum(r["spend_usd"] for r in silver), 2)
    published_spend = round(sum(g["spend_usd"] for g in published), 2)
    suppressed_spend = round(sum(g["spend_usd"] for g in suppressed), 2)
    summary = {
        "min_source_rows": min_source_rows,
        "total_groups": len(grouped),
        "published_groups": len(published),
        "suppressed_groups": len(suppressed),
        "published_spend_usd": published_spend,
        "suppressed_spend_usd": suppressed_spend,
        "silver_spend_usd": silver_spend,
        # Published + suppressed must reconcile back to the silver total.
        "reconciles": abs(published_spend + suppressed_spend - silver_spend) <= 0.01,
    }
    return {"published": published, "suppressed": suppressed, "summary": summary}


def privacy_summary_lines(rollup: dict) -> list[str]:
    """Render the privacy gate result as report lines."""
    s = rollup["summary"]
    lines = [
        "Privacy-safe rollup "
        f"(min {s['min_source_rows']} source events per group):",
        f"  Published groups: {s['published_groups']} of {s['total_groups']} "
        f"(${s['published_spend_usd']:,.2f} spend)",
        f"  Suppressed groups: {s['suppressed_groups']} "
        f"(${s['suppressed_spend_usd']:,.2f} spend held out)",
        f"  Reconciliation: {'PASS' if s['reconciles'] else 'FAIL'} "
        "— published + suppressed spend matches silver",
    ]
    for g in rollup["suppressed"]:
        lines.append(
            f"  Suppressed: {g['channel']} / {g['campaign_id']} — "
            f"{g['suppression_reason']}"
        )
    return lines
