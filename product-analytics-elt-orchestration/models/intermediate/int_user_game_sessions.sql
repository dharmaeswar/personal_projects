-- Intermediate model: play sessions joined to the game catalog.
-- This is the user-to-game signal: which users played which games, when.
SELECT
    s.session_id,
    s.user_id,
    s.game_id,
    c.title,
    c.genre,
    c.platform,
    s.session_date,
    s.duration_sec,
    s.event_count
FROM game_sessions_raw s
JOIN {{ ref('stg_game_catalog') }} c
  ON c.game_id = s.game_id
