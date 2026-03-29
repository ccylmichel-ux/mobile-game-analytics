{{ config(materialized='view') }}

SELECT *
FROM {{ ref('imd_install_count') }}
