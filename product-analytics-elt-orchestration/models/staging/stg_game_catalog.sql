-- Staging model: third-party game catalog (SensorTower-style fields:
-- publisher, genre, platform, store rank). Synthetic reference data,
-- seeded deterministically by product_analytics.models.seed_squad_sources.
SELECT
    game_id,
    title,
    publisher,
    genre,
    platform,
    store_rank,
    first_seen_date
FROM game_catalog_raw
