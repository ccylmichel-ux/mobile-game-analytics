{{ config(materialized='view') }}

WITH cohort AS (
    SELECT * FROM {{ ref('imd_user_cohort') }}
),

level_outcomes AS (
    SELECT
        s_user_id,
        event_name,
        level_id
    FROM {{ ref('imd_levels') }}
    WHERE event_name IN ('level_completed', 'level_failed')
),

outcomes_by_cohort AS (
    SELECT
        c.country,
        c.install_date,
        l.level_id,
        l.event_name
    FROM cohort AS c
    INNER JOIN level_outcomes AS l
        ON c.s_user_id = l.s_user_id
),

agg AS (
    SELECT
        country,
        install_date,
        level_id,
        COUNT(*) FILTER (WHERE event_name = 'level_completed')
            AS level_completions,
        COUNT(*) FILTER (WHERE event_name = 'level_failed')
            AS level_failures
    FROM outcomes_by_cohort
    GROUP BY 1, 2, 3
)

SELECT
    country,
    install_date,
    level_id,
    level_completions,
    level_failures,
    ROUND(
        100.0
        * level_completions
        / NULLIF(level_completions + level_failures, 0),
        2
    ) AS level_win_rate_pct
FROM agg
