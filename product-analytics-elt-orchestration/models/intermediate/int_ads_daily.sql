-- Intermediate model: daily ad delivery by campaign and channel.
SELECT
    campaign_id,
    campaign_name,
    channel,
    event_date,
    SUM(impressions) AS impressions,
    SUM(clicks) AS clicks,
    SUM(spend_usd) AS spend_usd
FROM {{ ref('stg_ads') }}
GROUP BY campaign_id, campaign_name, channel, event_date
