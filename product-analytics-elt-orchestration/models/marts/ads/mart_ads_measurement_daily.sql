-- Ads squad mart: impressions, clicks, spend, CTR and CPC by campaign
-- and channel. Grain: one row per (metric_date, campaign_id, channel).
-- Consumed by ads measurement and analytics for reporting and attribution.
SELECT
    event_date AS metric_date,
    campaign_id,
    campaign_name,
    channel,
    impressions,
    clicks,
    spend_usd,
    CASE WHEN impressions > 0
         THEN CAST(clicks AS REAL) / impressions END AS ctr,
    CASE WHEN clicks > 0
         THEN spend_usd / clicks END AS cpc
FROM {{ ref('int_ads_daily') }}
