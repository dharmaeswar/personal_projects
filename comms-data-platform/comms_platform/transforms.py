"""Transforms — the Glue (PySpark) job, modelled locally.

Each function names the Spark operation it mirrors so the code maps
one-to-one onto a real PySpark job (swap the pandas calls for Spark
equivalents and the logic is unchanged). Runs locally with pandas +
Parquet; no Spark cluster is involved and the code says so where it
matters.
"""

from __future__ import annotations

import pandas as pd


def build_daily_engagement(messages_df, metrics_df):
    """Gold: daily engagement by campaign and channel.

    Spark mapping:
      - messages deduped on message_id  -> ROW_NUMBER() OVER
        (PARTITION BY message_id ORDER BY send_date DESC), rn = 1
      - join metrics to messages         -> broadcast join on campaign_id
        (5-row campaign dimension; no shuffle)
      - group by event_date, campaign    -> GROUP BY with sum() / count()
      - open_rate                        -> withColumn(total_opens /
        audience) guarded against division by zero
    """
    msgs = messages_df.copy()
    msgs = msgs.sort_values("send_date").drop_duplicates("message_id", keep="last")
    audience = (
        msgs.groupby("campaign_id")["audience_size"].sum().rename("total_audience")
    )
    joined = metrics_df.merge(
        msgs[["campaign_id", "channel"]].drop_duplicates(),
        on="campaign_id",
        how="left",
    )
    grouped = (
        joined.groupby(["event_date", "campaign_id", "channel"], dropna=False)
        .agg(total_opens=("opens", "sum"), total_clicks=("clicks", "sum"))
        .reset_index()
    )
    counts = (
        msgs.groupby(["send_date", "campaign_id", "channel"])
        .size()
        .rename("messages_sent")
        .reset_index()
        .rename(columns={"send_date": "event_date"})
    )
    gold = grouped.merge(counts, on=["event_date", "campaign_id", "channel"], how="outer")
    gold = gold.fillna({"total_opens": 0, "total_clicks": 0, "messages_sent": 0})
    aud = audience.reset_index()
    gold = gold.merge(aud, on="campaign_id", how="left")
    gold["open_rate"] = gold.apply(
        lambda r: (r["total_opens"] / r["total_audience"]) if r["total_audience"] else 0.0,
        axis=1,
    )
    gold = gold.drop(columns=["total_audience"])
    gold = gold[
        [
            "event_date",
            "campaign_id",
            "channel",
            "messages_sent",
            "total_opens",
            "total_clicks",
            "open_rate",
        ]
    ]
    for col in ("messages_sent", "total_opens", "total_clicks"):
        gold[col] = gold[col].astype("int64")
    gold["open_rate"] = gold["open_rate"].astype("float64")
    gold = gold.sort_values(["event_date", "campaign_id"]).reset_index(drop=True)
    return gold
