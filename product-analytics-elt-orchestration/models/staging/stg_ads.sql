-- Staging model: ad delivery events with spend and clicks.
-- Rows that break the contract (negative spend, clicks above impressions)
-- never reach a mart; they are filtered here and counted by the tests.
SELECT
    campaign_id,
    campaign_name,
    channel,
    event_date,
    CAST(impressions AS INTEGER) AS impressions,
    CAST(clicks AS INTEGER) AS clicks,
    CAST(spend_usd AS REAL) AS spend_usd
FROM ads_raw
WHERE impressions >= 0
  AND clicks >= 0
  AND spend_usd >= 0
  AND clicks <= impressions
