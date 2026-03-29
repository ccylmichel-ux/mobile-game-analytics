{{ config(materialized='ephemeral') }}


WITH inst_base AS (
    SELECT
        s_user_id,
        s_country_code,
        s_event_client_timestamp
    FROM {{ ref('stg_installs') }}
),

level_base AS (
    SELECT
        s_user_id,
        s_country_code,
        s_event_client_timestamp
    FROM {{ ref('stg_levels') }}
),

install_first AS (
    SELECT
        s_user_id,
        ARG_MIN(s_country_code, s_event_client_timestamp) AS country,
        MIN(s_event_client_timestamp) AS cohort_date
    FROM inst_base
    GROUP BY s_user_id
),


level_first AS (    
    SELECT
        s_user_id,
        ARG_MIN(s_country_code, s_event_client_timestamp) AS country,
        MIN(s_event_client_timestamp) AS cohort_date
    FROM level_base
    GROUP BY s_user_id
),

cohort_assign AS (
    SELECT
        COALESCE(i.s_user_id, l.s_user_id) AS s_user_id,
        COALESCE(i.cohort_date, l.cohort_date) AS cohort_date,
        CASE
            WHEN i.s_user_id IS NOT NULL THEN 'install'
            ELSE 'first_level'
        END AS install_attribution,
        COALESCE(i.country, l.country) AS country
    FROM install_first AS i
    FULL OUTER JOIN level_first AS l ON i.s_user_id = l.s_user_id
)

SELECT
    s_user_id,
    install_attribution,
    country,
    CAST(cohort_date AS DATE) AS install_date
FROM cohort_assign
