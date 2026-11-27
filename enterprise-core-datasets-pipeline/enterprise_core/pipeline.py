"""Bronze -> silver -> gold pipeline for Enterprise Core Datasets.

Spark mapping (each pandas step names its Spark equivalent):
- dedupe: ROW_NUMBER() OVER (PARTITION BY <key> ORDER BY ingested_seq DESC)
- dims/facts: Spark SQL GROUP BY / joins against Parquet tables
- incremental load: watermark filter on the source date, append-only writes
- SCD Type 2: close the current dim row, open a new row with effective dates

Layers:
- bronze_<feed>: raw rows that passed the source contract, append-only.
- quarantine_<feed>: rows that broke the contract, kept with a reason.
- dim_tool (SCD2 on unit price), dim_team (SCD1), dim_date, dim_cost_category,
  dim_payment_method (SCD1).
- fact_ai_usage_daily, fact_unit_economics_daily, fact_cost_daily,
  fact_jira_weekly, fact_payments_daily.
"""

import pandas as pd

from . import seed as seed_mod
from .contracts import validate

FEEDS = ["ai_usage", "jira_issues", "bookings", "payments"]
KEY_FIELD = {"ai_usage": "event_id", "jira_issues": "issue_key", "bookings": "booking_id",
             "payments": "txn_id"}
DATE_FIELD = {"ai_usage": "event_date", "jira_issues": "updated_date", "bookings": "booking_date",
              "payments": "txn_date"}
COST_CATEGORIES = ["hosting", "support", "payment"]

LINEAGE = {
    "bronze_ai_usage": ["source:ai_usage_events"],
    "bronze_jira_issues": ["source:jira_api"],
    "bronze_bookings": ["source:bookings_db"],
    "bronze_payments": ["source:payments_gateway"],
    "dim_tool": ["bronze_ai_usage", "source:tool_price_contract"],
    "dim_team": ["bronze_ai_usage", "bronze_jira_issues"],
    "dim_date": ["bronze_ai_usage", "bronze_jira_issues", "bronze_bookings", "bronze_payments"],
    "dim_cost_category": ["bronze_bookings"],
    "dim_payment_method": ["bronze_payments"],
    "fact_ai_usage_daily": ["bronze_ai_usage", "dim_tool", "dim_team", "dim_date"],
    "fact_unit_economics_daily": ["bronze_bookings", "dim_date"],
    "fact_cost_daily": ["bronze_bookings", "dim_cost_category", "dim_date"],
    "fact_jira_weekly": ["bronze_jira_issues", "dim_date"],
    "fact_payments_daily": ["bronze_payments", "dim_payment_method", "dim_date"],
}


class Warehouse:
    """In-memory tables + watermarks; persisted to Parquet by run.py."""

    def __init__(self):
        self.tables = {}
        self.load_state = {}  # watermark per table: max source date loaded
        self.quarantine_counts = {}

    # ---- bronze ingest -------------------------------------------------
    def ingest(self, feed, rows):
        """Validate against the contract, dedupe, append to bronze_<feed>.

        Returns a dict of counts. Re-running with the same rows inserts 0 new
        rows: dedupe is on the natural key, so re-delivered batches collapse.
        """
        good, quarantined = validate(feed, rows)
        key = KEY_FIELD[feed]
        bronze_name = f"bronze_{feed}"
        existing = self.tables.get(bronze_name)
        if existing is not None and not existing.empty:
            combined = pd.concat([existing, pd.DataFrame(good)], ignore_index=True)
        else:
            combined = pd.DataFrame(good)
        before = len(combined)
        if not combined.empty:
            # ROW_NUMBER() OVER (PARTITION BY key ORDER BY _seq DESC), keep rn=1
            combined["_seq"] = range(len(combined))
            combined = combined.sort_values("_seq").drop_duplicates(key, keep="last")
            combined = combined.drop(columns=["_seq"]).reset_index(drop=True)
        self.tables[bronze_name] = combined
        self.quarantine_counts[feed] = self.quarantine_counts.get(feed, 0) + len(quarantined)
        self.tables[f"quarantine_{feed}"] = pd.DataFrame(quarantined)
        new_rows = len(combined) - (len(existing) if existing is not None else 0)
        return {"feed": feed, "received": len(rows), "good": len(good),
                "quarantined": len(quarantined), "new_bronze_rows": max(new_rows, 0),
                "duplicates_removed": before - len(combined)}

    # ---- dimensions ----------------------------------------------------
    def build_dims(self):
        """Build (or rebuild) dimensions. dim_tool is SCD Type 2."""
        tool_rows = []
        for tool, versions in seed_mod.PRICE_HISTORY.items():
            for i, (effective, price) in enumerate(versions):
                end = versions[i + 1][0] if i + 1 < len(versions) else "9999-12-31"
                from datetime import date, timedelta
                end_date = (date.fromisoformat(end) - timedelta(days=1)).isoformat() \
                    if end != "9999-12-31" else "9999-12-31"
                tool_rows.append({
                    "tool_key": f"{tool}@{effective}", "tool_name": tool,
                    "price_per_1k_tokens": price, "effective_from": effective,
                    "effective_to": end_date, "is_current": 1 if end == "9999-12-31" else 0,
                })
        self.tables["dim_tool"] = pd.DataFrame(tool_rows)

        teams = set()
        for feed in ("ai_usage", "jira_issues"):
            bronze = self.tables.get(f"bronze_{feed}")
            if bronze is not None and not bronze.empty and "team" in bronze.columns:
                teams.update(bronze["team"].dropna().unique().tolist())
        self.tables["dim_team"] = pd.DataFrame(
            [{"team": t} for t in sorted(teams)])

        dates = set()
        for feed in FEEDS:
            bronze = self.tables.get(f"bronze_{feed}")
            if bronze is not None and not bronze.empty:
                dates.update(bronze[DATE_FIELD[feed]].astype(str).unique().tolist())
        self.tables["dim_date"] = pd.DataFrame(
            [{"date": d} for d in sorted(dates)])
        self.tables["dim_cost_category"] = pd.DataFrame(
            [{"cost_category": c} for c in COST_CATEGORIES])
        pay = self.tables.get("bronze_payments")
        methods = sorted(pay["payment_method"].dropna().unique().tolist()) \
            if pay is not None and not pay.empty and "payment_method" in pay.columns else []
        self.tables["dim_payment_method"] = pd.DataFrame(
            [{"payment_method": m} for m in methods])

    def _price_on(self, tool, day_iso):
        return seed_mod.price_on(tool, day_iso)

    # ---- facts (incremental, watermarked) ------------------------------
    def build_facts(self):
        """Append-only incremental fact loads. Returns rows added per fact."""
        added = {}

        ai = self.tables.get("bronze_ai_usage")
        if ai is not None and not ai.empty:
            wm = self.load_state.get("fact_ai_usage_daily", "0000-00-00")
            new = ai[ai["event_date"].astype(str) > wm]
            if not new.empty:
                grouped = (new.groupby(["event_date", "tool_name", "team"], as_index=False)
                           .agg(events=("event_id", "count"),
                                tokens_in=("tokens_in", "sum"),
                                tokens_out=("tokens_out", "sum"),
                                cost_usd=("cost_usd", "sum")))
                grouped["price_per_1k_tokens"] = [
                    self._price_on(t, d) for t, d in
                    zip(grouped["tool_name"], grouped["event_date"].astype(str))]
                grouped = grouped.rename(columns={"event_date": "date"})
                prev = self.tables.get("fact_ai_usage_daily")
                self.tables["fact_ai_usage_daily"] = (
                    pd.concat([prev, grouped], ignore_index=True) if prev is not None
                    else grouped)
                self.load_state["fact_ai_usage_daily"] = str(new["event_date"].max())
                added["fact_ai_usage_daily"] = len(grouped)

        bk = self.tables.get("bronze_bookings")
        if bk is not None and not bk.empty:
            wm = self.load_state.get("fact_unit_economics_daily", "0000-00-00")
            new = bk[bk["booking_date"].astype(str) > wm]
            if not new.empty:
                ue = pd.DataFrame({
                    "date": new["booking_date"].astype(str),
                    "gbv_usd": new["gbv_usd"],
                    "revenue_usd": new["revenue_usd"],
                    "total_cost_usd": (new["hosting_cost_usd"] + new["support_cost_usd"]
                                       + new["payment_cost_usd"]),
                })
                ue["margin_usd"] = ue["revenue_usd"] - ue["total_cost_usd"]
                ue["margin_pct"] = (ue["margin_usd"] / ue["revenue_usd"]).round(4)
                prev = self.tables.get("fact_unit_economics_daily")
                self.tables["fact_unit_economics_daily"] = (
                    pd.concat([prev, ue], ignore_index=True) if prev is not None else ue)
                cost_rows = []
                for _, r in new.iterrows():
                    for cat, col in (("hosting", "hosting_cost_usd"),
                                     ("support", "support_cost_usd"),
                                     ("payment", "payment_cost_usd")):
                        cost_rows.append({"date": str(r["booking_date"]),
                                         "cost_category": cat, "amount_usd": r[col]})
                costs = pd.DataFrame(cost_rows)
                prev_c = self.tables.get("fact_cost_daily")
                self.tables["fact_cost_daily"] = (
                    pd.concat([prev_c, costs], ignore_index=True) if prev_c is not None
                    else costs)
                self.load_state["fact_unit_economics_daily"] = str(new["booking_date"].max())
                added["fact_unit_economics_daily"] = len(ue)
                added["fact_cost_daily"] = len(costs)

        ji = self.tables.get("bronze_jira_issues")
        if ji is not None and not ji.empty:
            wm = self.load_state.get("fact_jira_weekly", "0000-00-00")
            ji = ji.copy()
            ji["week_end"] = pd.to_datetime(ji["updated_date"]).dt.to_period("W").dt.end_time.dt.date.astype(str)
            new = ji[ji["week_end"] > wm]
            if not new.empty:
                weekly = (new.groupby(["week_end", "project_key", "status"], as_index=False)
                          .agg(open_issues=("issue_key", "count"),
                               story_points=("story_points", "sum")))
                prev = self.tables.get("fact_jira_weekly")
                self.tables["fact_jira_weekly"] = (
                    pd.concat([prev, weekly], ignore_index=True) if prev is not None
                    else weekly)
                self.load_state["fact_jira_weekly"] = str(new["week_end"].max())
                added["fact_jira_weekly"] = len(weekly)

        pay = self.tables.get("bronze_payments")
        if pay is not None and not pay.empty:
            wm = self.load_state.get("fact_payments_daily", "0000-00-00")
            new = pay[pay["txn_date"].astype(str) > wm]
            if not new.empty:
                settled = new[new["status"] == "settled"]
                grouped = (new.groupby(["txn_date", "payment_method", "status"], as_index=False)
                           .agg(txn_count=("txn_id", "count"),
                                gross_amount_usd=("amount_usd", "sum"),
                                settled_amount_usd=("settled_amount_usd", "sum")))
                lag = (settled.groupby(["txn_date", "payment_method"], as_index=False)
                       .agg(avg_settlement_lag_days=("settlement_lag_days", "mean")))
                grouped = grouped.merge(
                    lag, left_on=["txn_date", "payment_method"],
                    right_on=["txn_date", "payment_method"], how="left")
                grouped["avg_settlement_lag_days"] = (
                    grouped["avg_settlement_lag_days"].fillna(0.0).round(2))
                # Settlement lag is meaningful only on settled rows.
                grouped.loc[grouped["status"] != "settled",
                            "avg_settlement_lag_days"] = 0.0
                grouped = grouped.rename(columns={"txn_date": "date"})
                prev = self.tables.get("fact_payments_daily")
                self.tables["fact_payments_daily"] = (
                    pd.concat([prev, grouped], ignore_index=True) if prev is not None
                    else grouped)
                self.load_state["fact_payments_daily"] = str(new["txn_date"].max())
                added["fact_payments_daily"] = len(grouped)
        return added

    def lineage_for(self, table, exclude=frozenset()):
        """Upstream sources for a table (used by backfill planning).

        Tables in ``exclude`` (e.g. shared dims like dim_date) are not
        traversed: a backfill of one source does not rebuild dimensions that
        merely list its dates.
        """
        seen, stack = [], [table]
        while stack:
            node = stack.pop()
            for parent in LINEAGE.get(node, []):
                if parent in exclude or parent in seen:
                    continue
                seen.append(parent)
                stack.append(parent)
        return seen
