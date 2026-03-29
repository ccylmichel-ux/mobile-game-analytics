{{ config(materialized='view') }}

SELECT *
FROM {{ ref('imd_levels') }}
