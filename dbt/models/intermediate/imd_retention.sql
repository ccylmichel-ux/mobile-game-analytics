{{ config(materialized='view') }}

-- D1 / D7 by country + install_date. Retained at DX iff at least one level_started /
-- level_completed / level_failed on calendar day install_date + X (same convention as
-- imd_user_cohort.install_date). JOIN + MAX(...) per user is equivalent to EXISTS;
-- plain JOIN without GROUP BY would duplicate users and break COUNT(*) as installs.

WITH cohort AS (
    SELECT
        s_user_id,
        country,
        install_date
    FROM {{ ref('imd_user_cohort') }}
),

activity_days AS (
    SELECT DISTINCT
        s_user_id,
        CAST(s_event_client_timestamp AS DATE) AS activity_date
    FROM {{ ref('stg_levels') }}
),

user_retention AS (
    SELECT
        c.s_user_id,
        c.country,
        c.install_date,
        MAX(
            CASE
                WHEN a.activity_date = c.install_date + 1 THEN 1 ELSE 0
            END
        ) AS retained_d1,
        MAX(
            CASE
                WHEN a.activity_date = c.install_date + 7 THEN 1 ELSE 0
            END
        ) AS retained_d7
    FROM cohort AS c
    LEFT JOIN activity_days AS a
        ON
            c.s_user_id = a.s_user_id
            AND a.activity_date > c.install_date
            AND a.activity_date <= c.install_date + 7
    GROUP BY c.s_user_id, c.country, c.install_date
)

SELECT
    country,
    install_date,
    COUNT(*) AS installs,
    SUM(retained_d1) AS day_1_retention,
    SUM(retained_d7) AS day_7_retention
FROM user_retention
GROUP BY 1, 2
