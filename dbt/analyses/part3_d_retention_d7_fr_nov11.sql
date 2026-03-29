-- 3d) Retention D7 for French users that installed on 11 Nov 2025.

SELECT
    country,
    install_date,
    installs,
    day_7_retention,
    ROUND(100.0 * day_7_retention / NULLIF(installs, 0), 2) AS retention_d7_pct
FROM {{ ref('mart_retention') }}
WHERE
    country = 'FR'
    AND install_date = DATE '2025-11-11'
