-- 3c) Win rate of level 25 for users that installed on 2 Nov 2025.

SELECT
    level_id,
    SUM(level_completions) AS level_completions,
    SUM(level_failures) AS level_failures,
    ROUND(
        100.0 * SUM(level_completions)
        / NULLIF(SUM(level_completions) + SUM(level_failures), 0),
        2
    ) AS level_win_rate_pct
FROM {{ ref('mart_level_win_rate') }}
WHERE
    level_id = 25
    AND install_date = DATE '2025-11-02'
GROUP BY level_id
