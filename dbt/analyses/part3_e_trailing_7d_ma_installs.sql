-- 3e) Trailing 7-day moving average of installs per day.

WITH daily AS (
    SELECT
        install_date,
        SUM(install_count) AS installs_that_day
    FROM {{ ref('mart_install_count') }}
    GROUP BY install_date
)

SELECT
    install_date,
    installs_that_day,
    ROUND(
        AVG(installs_that_day) OVER (
            ORDER BY install_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS trailing_7d_ma_installs
FROM daily
ORDER BY install_date