{{ config(materialized='view') }}

SELECT *
FROM {{ ref('imd_user_cohort') }}
