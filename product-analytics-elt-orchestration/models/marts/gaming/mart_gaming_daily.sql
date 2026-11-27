-- Gaming squad mart: daily active gamers, sessions and play minutes by game.
-- Grain: one row per (metric_date, game_id). Consumed by game teams and
-- data science for engagement analysis and experimentation readouts.
SELECT
    session_date AS metric_date,
    game_id,
    title,
    genre,
    platform,
    COUNT(DISTINCT user_id) AS daily_active_gamers,
    COUNT(*) AS sessions,
    SUM(duration_sec) / 60.0 AS play_minutes,
    AVG(duration_sec) / 60.0 AS avg_session_minutes
FROM {{ ref('int_user_game_sessions') }}
GROUP BY session_date, game_id, title, genre, platform
