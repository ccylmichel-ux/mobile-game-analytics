{{ config(materialized='view') }}

SELECT
    s_country_code AS country,
    CAST(s_event_client_timestamp AS DATE) AS install_date,
    COUNT(*) AS install_count
FROM {{ ref('stg_installs') }}
GROUP BY 1, 2
