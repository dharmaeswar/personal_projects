-- Staging model: one row per contract-valid product event.
-- Source: staged_events (already contract-checked and deduplicated upstream).
SELECT DISTINCT
    event_id,
    user_id,
    event_type,
    event_ts,
    substr(event_ts, 1, 10) AS event_date,
    payload
FROM staged_events
