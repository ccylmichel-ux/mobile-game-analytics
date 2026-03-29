-- 3a) Average installs per day for each country during November (2025).
-- Interpretation: total install events in Nov / 30 days per country.

SELECT
    country,
    ROUND(SUM(install_count) / 30.0, 1) AS avg_installs_per_day_november
FROM {{ ref('mart_install_count') }}
GROUP BY country
ORDER BY country
