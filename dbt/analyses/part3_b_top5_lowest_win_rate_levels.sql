-- 3b) Top 5 lowest win rate levels with their win rate.

SELECT
    level_id,
    ROUND(
        100.0 * SUM(level_completions)
        / NULLIF(SUM(level_completions) + SUM(level_failures), 0),
        4
    ) AS win_rate
FROM {{ ref('mart_level_win_rate') }}
GROUP BY level_id
ORDER BY win_rate ASC
LIMIT 5
