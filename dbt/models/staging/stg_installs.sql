
{{ config(
    materialized='incremental',
    incremental_strategy='append',
) }}

SELECT
    d_event_received::date AS d_event_received,
    i_timestamp::bigint AS i_timestamp,
    (TRIM(s_event_client_timestamp::varchar))::timestamp AS s_event_client_timestamp,
    TRIM(s_user_id::varchar) AS s_user_id,
    TRIM(s_country_code::varchar) AS s_country_code,
    TRIM(s_event_name::varchar) AS s_event_name,
    TRIM(s_event_value::varchar) AS s_event_value
FROM READ_PARQUET(
    '{{ var("raw_installs_glob") }}',
    hive_partitioning = true,
    union_by_name = true
)
WHERE
    s_user_id IS NOT NULL
    {{ partition_incremental_after_max('d_event_received') }}
