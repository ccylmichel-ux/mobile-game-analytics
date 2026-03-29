{#- Même logique incrémentale que stg_installs (nouvelles partitions seulement). -#}
{{ config(
    materialized='incremental',
    incremental_strategy='append',
) }}

WITH base AS (
    SELECT
        d_event_received::date AS d_event_received,
        i_timestamp::bigint AS i_timestamp,
        TRIM(s_user_id::varchar) AS s_user_id,
        TRIM(s_country_code::varchar) AS s_country_code,
        CAST(TRIM(s_event_client_timestamp::varchar) AS TIMESTAMP) AS s_event_client_timestamp,
        LOWER(TRIM(s_event_name::varchar)) AS s_event_name,
        TRIM(s_event_value::varchar) AS s_event_value
    FROM READ_PARQUET(
        '{{ var("raw_levels_glob") }}',
        hive_partitioning = true,
        union_by_name = true
    )
    WHERE
        s_event_name IN ('level_started', 'level_completed', 'level_failed')
        AND s_user_id IS NOT NULL
        {{ partition_incremental_after_max('d_event_received') }}
)

SELECT * FROM base
