{{ config(materialized='view') }}

WITH base AS (
    SELECT
        s_user_id,
        s_country_code AS country,
        s_event_name AS event_name,
        CAST(s_event_client_timestamp AS DATE) AS event_date,
        CAST(JSON_EXTRACT(s_event_value, '$.level_id') AS INTEGER) AS level_id
    FROM {{ ref('stg_levels') }}
)

SELECT * FROM base
