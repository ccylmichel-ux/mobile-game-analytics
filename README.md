# Mobile game analytics (Homa case study)

dbt + DuckDB project for staging and marts over Parquet event data. 
---

## Zip deliverable — how to run locally (exact commands)

### Prerequisites

- Python **3.10+**, repo root = project root (e.g. `mobile-game-analytics/`).
- Raw Parquet under `data/raw/installs/**` and `data/raw/levels/**` (paths match `dbt/dbt_project.yml` `vars`). **Source:** download from the URLs in **`Homa DE case study.pdf`** (Hive partitions for November 2025).
- Optional env: `HOMA_DUCKDB_PATH` — defaults to `warehouse/homa.duckdb` relative to repo root (see `dbt/profiles.yml`).

### 1) Virtualenv and install

```bash
cd /path/to/mobile-game-analytics
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) SQL style check (SQLFluff)

From the **repo root** (config is in `.sqlfluff`):

```bash
sqlfluff lint dbt/models dbt/analyses
```

### 3) Compile and run dbt (ingestion + transformation)

All commands from **`dbt/`** unless noted.

```bash
cd dbt
dbt compile    # parses project, resolves refs; compiled SQL in target/compiled/
dbt run        # builds staging (incremental Parquet → tables), intermediate, marts (views)
dbt test       # schema tests on models (e.g. not_null); optional
```

- **First run** after changing staging logic or existing warehouse:  
  `dbt run --full-refresh --select stg_installs stg_levels` then `dbt run`.
- **DuckDB lock:** close Streamlit / other DuckDB sessions on `warehouse/homa.duckdb` before `dbt run` / `dbt test`.

### 4.a) Case-study metrics — `analyses/` SQL 

Ad-hoc SQL lives in `dbt/analyses/part3_*.sql` (uses `{{ ref('mart_*') }}`). After **`dbt compile`**, run a compiled file against the warehouse (paths use project name `homa_analytics`):

```bash
cd dbt
dbt compile
duckdb ../warehouse/homa.duckdb < target/compiled/homa_analytics/analyses/part3_a_avg_installs_per_day.sql
```

Repeat with `part3_b_…` through `part3_e_…` as needed. Alternatively open the same files in DuckDB CLI/UI or paste into any SQL client attached to `homa.duckdb`.

### 4.b) Streamlit dashboard (optional UI over the same marts)

From **repo root**:

```bash
source .venv/bin/activate
streamlit run streamlit_app.py
```

The app reads `dbt/analyses/part3_*.sql`, resolves `ref()` to `main.mart_*`, and queries DuckDB. If Parquet paths break, run from repo root or set `HOMA_DBT_PROJECT_DIR` to the absolute path of `dbt/` (see `streamlit_app.py` docstring).

---

## Assumptions and trade-offs (short)

| Topic | Choice |
|--------|--------|
| **Event time** | `s_event_client_timestamp` (client) for player-facing metrics; `d_event_received` is Hive ingestion partition only. |
| **Cohorts / `install_date`** | Calendar date from client time in marts; users without install in-window use a **first-level** proxy (documented below). |
| **Staging** | **Incremental** `append` on new `d_event_received` partitions; late files in an **already loaded** day need `dbt run --full-refresh --select stg_installs stg_levels`. |
| **Warehouse** | Single-file DuckDB; good for local case study, not a distributed lake. |
| **Data quality report** | **Not implemented** (no DQ notebook or extra report beyond optional `dbt test` on YAML rules). |

Further detail: retention definition, install vs level-only users, and SQL audits are in the sections below.

---

## Data model 

| Layer | What it is |
|--------|------------|
| **Staging** | `stg_installs`, `stg_levels` — read Hive-partitioned Parquet (`READ_PARQUET`), filter null users / level event names. |
| **Intermediate** | `imd_*` — cohort (`imd_user_cohort`, ephemeral), installs per day/country, level events, retention, level win rates. |
| **Marts** | `mart_*` — thin **views** on `imd_*` for analytics and `analyses/`. |

DAG: raw Parquet → staging tables → intermediate (views/ephemeral) → marts (views).

---

## For reviewers: alignment with the Homa case study brief

This maps the PDF requirements to concrete artifacts so a supervisor can verify coverage quickly.

| Brief requirement | Where in this repo |
|-------------------|---------------------|
| **(1) Ingest & normalize** (types, timestamps, **idempotent re-runs**) | `dbt/models/staging/stg_installs.sql`, `stg_levels.sql`. **Idempotence:** incremental loads append **new** `d_event_received` partitions; use `dbt run --full-refresh --select stg_installs stg_levels` to rebuild staging from scratch or to reload a partition day that was already loaded. |
| **(2) Analytics-ready datasets** (install counts, level events, retention, win rate) | `dbt/models/intermediate/imd_*.sql` and thin **`mart_*`** views in `dbt/models/marts/`. |
| **(3) Derived metrics (a)–(e)** | SQL in **`dbt/analyses/part3_*.sql`** (executable after `dbt compile` — see [Zip deliverable](#zip-deliverable--how-to-run-locally-exact-commands)). Optional UI: **`streamlit_app.py`**. |
| **(4) Bonus: incremental partitions** | Documented in [Bonus: incremental ingestion](#bonus-incremental-ingestion-without-rebuilding-everything). |
| **(4) Bonus: DQ report** | **Not implemented** (acceptable per brief: “if you performed any”). Optional checks: `dbt test`. |
| **Raw data** | Case study lists **S3 HTTP URLs** for November 2025 Parquet. Download into **`data/raw/installs/`** and **`data/raw/levels/`** preserving Hive-style folders (`d_event_received=YYYY-MM-DD/…`). Paths must match `dbt_project.yml` `vars`. |

**Note:** The long sections below spell out **assumptions** (canonical client time, cohort / install attribution, retention definition) in the depth the brief asks for. The opening [Zip deliverable](#zip-deliverable--how-to-run-locally-exact-commands) block is the **minimal runbook** for a local reproduction.

---

## Canonical event time & retention (DX)

**Canonical time:** `s_event_client_timestamp` (client) is the event time for player-facing metrics. `i_timestamp` and `d_event_received` are **server / ingestion** time; after offline play they can lag real activity, so using them would bias day-based metrics. **`install_date`** in marts is the **calendar date** of that client time (cohort / activity day)—**not** the Hive partition date `d_event_received`.

**Retention D X:** A user is retained at **D X** if they **start or finish at least one level** on calendar day `cohort_date + X` (UTC), using the same level event types as in staging (`level_started`, `level_completed`, `level_failed`).

---

## Install date attribution & cohorting

**Brief:** Some users have level events but **no install row** in the window. We **approximate** cohort for those users from their first level event’s client time, and document bias (see below). SQL to reproduce counts: [Appendix A.1](#a1-distinct-install-users-and-overlap-with-levels).

### User counts (this extract, valid `s_user_id` where noted)

| Segment | Count | Notes |
|--------|------:|-------|
| Distinct users in **installs** | 4 739 | ≥1 install row |
| Distinct users in **levels** (`stg_levels`) | 11 429 | Named level events only |
| **Both** installs and levels | 4 713 | Intersection |
| **Install only** (no level rows) | 26 | |
| **Level only** (no install row; valid id) | 6 716 | Brief’s “install unobservable” case (id-level) |

**`imd_user_cohort`** is a **FULL OUTER JOIN** of first install time vs first level time per user (`install_attribution` = `install` | `first_level`). That is **not** the same as “users in both streams”: **`install`** = 4 739 (includes 4 713 + 26 install-only). **`first_level`** = **6 717** rows: level-side users **without** an install row (cohort from first level). **6 716** have a valid id; the extra row is a **NULL** user key from level rows that still reach `level_first` in this extract—add the same id filter in cohort logic if you need **6 716** to match exactly.

**Rule:** If the user has an install in-window, cohort = **MIN(client time on installs)** → date. If not, cohort = **MIN(client time on levels)** → date (proxy). **Support:** among the 4 713 in both streams, 4 710 (**99.94 %**) share the same calendar day for install-based cohort vs first level day.

**Proxy risks:** Pre-window installs with late first level in-window look like a **new** cohort; label or split by `install_attribution`, or publish install-only retention. **Rare overlap mismatch:** 3 users (0.06 % of 4 713) differ on install-day vs first-level-day (e.g. reinstall)—negligible for aggregates.

**Stricter alternative:** Drop level-only users from install-based metrics → clean definition but **undercount** anyone missing from the install feed.

---

## Appendix A: SQL & audit results

### A.1 Distinct install users and overlap with levels

```sql
WITH inst_users AS (
  SELECT DISTINCT s_user_id
  FROM {{ ref('stg_installs') }}
  WHERE s_user_id IS NOT NULL AND TRIM(CAST(s_user_id AS VARCHAR)) != ''
),
level_users AS (
  SELECT DISTINCT s_user_id
  FROM {{ ref('stg_levels') }}
  WHERE s_user_id IS NOT NULL AND TRIM(CAST(s_user_id AS VARCHAR)) != ''
)
SELECT
  (SELECT COUNT(*) FROM inst_users) AS distinct_install_users,
  (SELECT COUNT(*) FROM level_users) AS distinct_level_users,
  (SELECT COUNT(*) FROM inst_users i INNER JOIN level_users l ON i.s_user_id = l.s_user_id) AS users_in_both_streams,
  (
    SELECT COUNT(*)
    FROM level_users l
    LEFT JOIN inst_users i ON l.s_user_id = i.s_user_id
    WHERE i.s_user_id IS NULL
  ) AS level_only_users_no_install
```

**Latest run (this extract):**

| distinct_install_users | distinct_level_users | users_in_both_streams | level_only_users_no_install |
|-------------------------|----------------------:|----------------------:|----------------------:|
| 4 739 | 11 429 | 4 713 | 6 716 |

### A.2 Same calendar day: install cohort vs first level day

Per user: install day = `MIN(s_event_client_timestamp)` on installs → date; first level day = `MIN(s_event_client_timestamp)` on levels → date. Filter valid `s_user_id` as above.

```sql
WITH inst AS (
  SELECT
    s_user_id,
    CAST(MIN(s_event_client_timestamp) AS DATE) AS install_date
  FROM {{ ref('stg_installs') }}
  WHERE s_user_id IS NOT NULL AND TRIM(CAST(s_user_id AS VARCHAR)) != ''
  GROUP BY 1
),
evt AS (
  SELECT
    s_user_id,
    CAST(MIN(s_event_client_timestamp) AS DATE) AS first_event_date
  FROM {{ ref('stg_levels') }}
  WHERE s_user_id IS NOT NULL AND TRIM(CAST(s_user_id AS VARCHAR)) != ''
  GROUP BY 1
),
per_user AS (
  SELECT i.s_user_id, i.install_date, e.first_event_date
  FROM inst i
  INNER JOIN evt e ON i.s_user_id = e.s_user_id
)
SELECT
  COUNT(*) AS users_in_scope,
  COUNT(*) FILTER (WHERE first_event_date = install_date) AS same_calendar_day,
  ROUND(100.0 * COUNT(*) FILTER (WHERE first_event_date = install_date) / NULLIF(COUNT(*), 0), 2) AS pct_same_day
FROM per_user
```

**Latest run:**

| users_in_scope | same_calendar_day | pct_same_day |
|----------------|------------------:|-------------:|
| 4 713 | 4 710 | 99.94 |

*Note:* For production, derive **UTC dates** explicitly (DuckDB `timezone` / `AT TIME ZONE`) so this matches the written “UTC calendar days” rule; `CAST(... AS DATE)` follows session semantics.

### A.3 Users where install day ≠ first level day

```sql
WITH inst AS (
  SELECT
    s_user_id,
    CAST(MIN(s_event_client_timestamp) AS DATE) AS install_date
  FROM {{ ref('stg_installs') }}
  WHERE s_user_id IS NOT NULL AND TRIM(CAST(s_user_id AS VARCHAR)) != ''
  GROUP BY 1
),
evt AS (
  SELECT
    s_user_id,
    CAST(MIN(s_event_client_timestamp) AS DATE) AS first_event_date
  FROM {{ ref('stg_levels') }}
  WHERE s_user_id IS NOT NULL AND TRIM(CAST(s_user_id AS VARCHAR)) != ''
  GROUP BY 1
),
per_user AS (
  SELECT i.s_user_id, i.install_date, e.first_event_date
  FROM inst i
  INNER JOIN evt e ON i.s_user_id = e.s_user_id
)
SELECT
  s_user_id,
  install_date,
  first_event_date,
  first_event_date - install_date AS day_diff,
  ABS(first_event_date - install_date) AS abs_day_diff
FROM per_user
WHERE first_event_date != install_date
ORDER BY abs_day_diff DESC, s_user_id
```

**Latest run (3 rows):**

| install_date | first_event_date | day_diff | abs_day_diff |
|--------------|------------------|---------:|-------------:|
| 2025-08-16 | 2025-01-05 | −223 | 223 |
| 2025-11-26 | 2025-11-19 | −7 | 7 |
| 2025-11-24 | 2025-11-30 | 6 | 6 |

### A.4 Install staging row quality (optional)

```sql
SELECT
  COUNT(*) AS total_rows,
  SUM(CASE WHEN s_user_id IS NULL OR TRIM(CAST(s_user_id AS VARCHAR)) = '' THEN 1 ELSE 0 END) AS null_or_empty_user_id,
  SUM(CASE WHEN s_event_client_timestamp IS NULL THEN 1 ELSE 0 END) AS null_client_timestamp
FROM {{ ref('stg_installs') }}
```

**Latest run:** 0 null/empty user ids and 0 null client timestamps on installs in this warehouse build (row count may exceed distinct users because of multiple install events per user).

---

## Bonus: incremental ingestion (without rebuilding everything)

### Where is incremental used?

- **Staging only:** `stg_installs` and `stg_levels` are **`incremental`** tables with **`append`**. On each `dbt run`, only **new partition dates** (`d_event_received`, Hive-style folders) **after** the latest date already loaded are read and **appended**—you do not reload all historical Parquet every time.
- **Marts (`mart_*`) and intermediate (`imd_*`):** these are **views** (or ephemeral models) on top of staging. They **reflect the staging tables automatically** as staging grows—**no** separate incremental config is required.

### When to use `--full-refresh`

- First deployment, or after changing staging columns / logic.
- **Late-arriving files** for a **partition date already loaded:** incremental runs will **not** re-read that day. Then run:  
  `dbt run --full-refresh --select stg_installs stg_levels` followed by `dbt run`.

```bash
cd dbt
dbt run                                    # load new partitions only
dbt run --full-refresh --select stg_installs stg_levels   # re-read all Parquet for staging
dbt run
```

### Data quality

Optional checks use **`dbt test`** (rules in model `.yml` files). Close Streamlit / DuckDB CLI if the `.duckdb` file is locked before `dbt run` / `dbt test`.
