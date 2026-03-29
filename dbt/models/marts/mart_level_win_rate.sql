{{ config(materialized='view') }}

SELECT *
FROM {{ ref('imd_level_win_rate') }}
