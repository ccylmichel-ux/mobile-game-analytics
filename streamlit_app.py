from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)
import plotly.graph_objects as go
import streamlit as st

_REPO_ROOT = Path(__file__).resolve().parent
_DBT_DIR = _REPO_ROOT / "dbt"
_ANALYSES_DIR = _DBT_DIR / "analyses"

_RE_REF = re.compile(
    r"\{\{\s*ref\(\s*['\"](?P<name>[\w_]+)['\"]\s*\)\s*\}\}",
    re.MULTILINE,
)

_BAR_COLOR = "#4FC3F7"
_BAR_LINE = "rgba(255,255,255,0.35)"
_GRID = "rgba(255,255,255,0.09)"
_PLOT_BG = "rgba(32, 36, 44, 0.55)"
_LINE_COLORS = ("#4FC3F7", "#FFB74D")

_NOV_START = pd.Timestamp("2025-11-01")
_NOV_END = pd.Timestamp("2025-12-01")


def _db_path() -> Path:
    env = os.environ.get("HOMA_DUCKDB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return _REPO_ROOT / "warehouse" / "homa.duckdb"


def _dbt_schema() -> str:
    return os.environ.get("HOMA_DBT_SCHEMA", "main")


def _compile_analysis_sql(raw: str) -> str:
    schema = _dbt_schema()

    def _repl(m: re.Match[str]) -> str:
        return f"{schema}.{m.group('name')}"

    return _RE_REF.sub(_repl, raw)


def load_analysis_sql(filename: str) -> str:
    path = _ANALYSES_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing analysis file: {path}")
    return _compile_analysis_sql(path.read_text(encoding="utf-8"))


@st.cache_resource
def _connect():
    path = _db_path()
    if not path.exists():
        return None
    return duckdb.connect(str(path), read_only=True)


@contextmanager
def _duckdb_read_parquet_cwd():
    dbt_dir = Path(os.environ.get("HOMA_DBT_PROJECT_DIR", str(_DBT_DIR))).resolve()
    prev = os.getcwd()
    os.chdir(dbt_dir)
    try:
        yield
    finally:
        os.chdir(prev)


def _q(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    with _duckdb_read_parquet_cwd():
        return con.execute(sql).df()


def _base_chart_layout(*, height: int = 340, margin: dict | None = None) -> dict:
    m = dict(l=56, r=28, t=40, b=64)
    if margin:
        m.update(margin)
    return dict(
        height=height,
        margin=m,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=_PLOT_BG,
        xaxis_showgrid=True,
        yaxis_showgrid=True,
        xaxis_gridcolor=_GRID,
        yaxis_gridcolor=_GRID,
        xaxis_zeroline=False,
        yaxis_zeroline=False,
        bargap=0.45,
    )


def _plotly_bar_categories_metric(df: pd.DataFrame, x_col_idx: int = 0, y_col_idx: int = 1) -> go.Figure:
    if len(df.columns) < 2:
        return go.Figure()
    xc, yc = df.columns[x_col_idx], df.columns[y_col_idx]
    x = df.iloc[:, x_col_idx].astype(str)
    y = df.iloc[:, y_col_idx]
    txt = y.map(lambda v: f"{float(v):.2f}" if pd.notna(v) else "")
    fig = go.Figure(
        data=[
            go.Bar(
                x=x,
                y=y,
                text=txt,
                textposition="outside",
                cliponaxis=False,
                marker=dict(color=_BAR_COLOR, line=dict(width=1, color=_BAR_LINE)),
            )
        ]
    )
    fig.update_layout(
        **_base_chart_layout(height=320, margin=dict(b=88)),
        showlegend=False,
        xaxis_title=xc,
        yaxis_title=yc,
        xaxis_tickangle=0,
        yaxis_rangemode="tozero",
    )
    return fig


def _plotly_bar_levels_winrate_horizontal(df: pd.DataFrame) -> go.Figure:
    if len(df.columns) < 2:
        return go.Figure()
    id_col, rate_col = df.columns[0], df.columns[1]
    d = df.iloc[::-1].reset_index(drop=True)
    y = d[id_col].astype(str)
    x = pd.to_numeric(d[rate_col], errors="coerce")
    txt = x.map(lambda v: f"{float(v):.2f}%" if pd.notna(v) else "")
    fig = go.Figure(
        data=[
            go.Bar(
                x=x,
                y=y,
                orientation="h",
                text=txt,
                textposition="outside",
                cliponaxis=False,
                marker=dict(color=_BAR_COLOR, line=dict(width=1, color=_BAR_LINE)),
            )
        ]
    )
    fig.update_layout(
        **_base_chart_layout(height=max(260, 52 * len(d) + 120), margin=dict(l=24, r=56, t=40, b=56)),
        showlegend=False,
        xaxis_title=str(rate_col) + " (%)",
        yaxis_title=str(id_col),
        yaxis_type="category",
        xaxis_tickangle=0,
        xaxis_rangemode="tozero",
    )
    fig.update_yaxes(automargin=True)
    fig.update_xaxes(automargin=True)
    return fig


def _plotly_line(df: pd.DataFrame, date_col: str, value_cols: list[str]) -> go.Figure:
    fig = go.Figure()
    for i, c in enumerate(value_cols):
        fig.add_trace(
            go.Scatter(
                x=df[date_col],
                y=df[c],
                mode="lines",
                name=c,
                line=dict(width=2, color=_LINE_COLORS[i % len(_LINE_COLORS)]),
            )
        )
    fig.update_layout(
        **_base_chart_layout(height=360, margin=dict(b=72)),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis_tickangle=0,
        xaxis_title="Date",
    )
    return fig


def _plotly_chart(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch")


def _inject_centered_layout_css() -> None:
    st.markdown(
        """
        <style>
            .main .block-container {
                max-width: 56rem;
                margin-left: auto !important;
                margin-right: auto !important;
                padding-left: 1.5rem;
                padding-right: 1.5rem;
            }
            .main h1, .main h2, .main h3 { text-align: center; }
            .main [data-testid="stCaptionContainer"],
            .main [data-testid="stCaptionContainer"] p { text-align: center; }
            /* Onglets : alignés à gauche, style « boutons » cliquables */
            .stTabs [data-baseweb="tab-list"],
            .stTabs [role="tablist"] {
                justify-content: flex-start !important;
                align-items: stretch;
                gap: 0.45rem;
                flex-wrap: wrap;
                padding: 0.6rem 0.75rem;
                margin-bottom: 0.25rem;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
            }
            .stTabs [data-baseweb="tab"],
            .stTabs button[role="tab"] {
                border-radius: 8px !important;
                padding: 0.45rem 0.75rem !important;
                margin: 0 !important;
                font-weight: 600 !important;
                font-size: 0.9rem !important;
                line-height: 1.35 !important;
                border: 1px solid rgba(255, 255, 255, 0.18) !important;
                background: rgba(255, 255, 255, 0.07) !important;
                color: rgba(255, 255, 255, 0.88) !important;
                transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
                cursor: pointer !important;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
            }
            .stTabs [data-baseweb="tab"]:hover,
            .stTabs button[role="tab"]:hover {
                background: rgba(79, 195, 247, 0.12) !important;
                border-color: rgba(79, 195, 247, 0.45) !important;
            }
            .stTabs [data-baseweb="tab"][aria-selected="true"],
            .stTabs button[role="tab"][aria-selected="true"] {
                background: rgba(79, 195, 247, 0.22) !important;
                border-color: #4FC3F7 !important;
                color: #fff !important;
                box-shadow: 0 0 0 1px rgba(79, 195, 247, 0.35), 0 2px 8px rgba(0, 0, 0, 0.25);
            }
            .main div[data-testid="stDataFrame"] {
                margin-left: auto !important;
                margin-right: auto !important;
                width: fit-content !important;
                max-width: 100%;
            }
            .main div[data-testid="stPlotlyChart"] {
                margin-left: auto !important;
                margin-right: auto !important;
            }
            .main div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
                justify-content: center;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _col_ci(df: pd.DataFrame, name: str) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    return lower.get(name.lower())


def _column_width_from_title(name: str, *, min_for_dates: bool = False) -> str:
    n = len(str(name))
    if n <= 12:
        w = "small"
    elif n <= 22:
        w = "medium"
    else:
        w = "large"
    if min_for_dates and w == "small":
        return "medium"
    return w


def _compact_dataframe(df: pd.DataFrame | None) -> None:
    if df is None:
        return
    if len(df.columns) == 0:
        st.dataframe(df, width="content", hide_index=True)
        return
    cfg: dict = {}
    for col in df.columns:
        s = df[col]
        w = _column_width_from_title(col)
        if is_datetime64_any_dtype(s):
            w = _column_width_from_title(col, min_for_dates=True)
            cfg[col] = st.column_config.DatetimeColumn(col, width=w, format="YYYY-MM-DD")
        elif is_bool_dtype(s):
            cfg[col] = st.column_config.CheckboxColumn(col, width=w)
        elif is_numeric_dtype(s):
            fmt = "%d" if pd.api.types.is_integer_dtype(s) else "%.2f"
            cfg[col] = st.column_config.NumberColumn(col, format=fmt, width=w)
        else:
            cfg[col] = st.column_config.TextColumn(col, width=w)
    st.dataframe(df, width="content", hide_index=True, column_config=cfg)


def _run_analysis(con: duckdb.DuckDBPyConnection, filename: str) -> tuple[pd.DataFrame | None, str]:
    sql = load_analysis_sql(filename)
    try:
        return _q(con, sql), sql
    except Exception as e:
        st.error(str(e))
        return None, sql


def _sql_expander(sql: str) -> None:
    with st.expander("SQL"):
        st.code(sql.strip(), language="sql")


def _metrics_row_c(df: pd.DataFrame | None) -> None:
    if df is None or len(df) < 1:
        return
    row = df.iloc[0]
    lc = _col_ci(df, "level_completions")
    lf = _col_ci(df, "level_failures")
    wr = _col_ci(df, "level_win_rate_pct")
    if not (lc and lf and wr):
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Completed", int(row[lc]))
    c2.metric("Failures", int(row[lf]))
    c3.metric("Win rate %", f"{float(row[wr]):.2f}")


def _metrics_row_d(df: pd.DataFrame | None) -> None:
    if df is None or len(df) < 1:
        return
    r = df.iloc[0]
    ins = _col_ci(df, "installs")
    d7 = _col_ci(df, "day_7_retention")
    pct = _col_ci(df, "retention_d7_pct")
    if not (ins and d7 and pct):
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Installs", int(r[ins]))
    c2.metric("Retained D7", int(r[d7]))
    c3.metric("Retention D7 %", f"{float(r[pct]):.2f}")


def _tab_line_november(df: pd.DataFrame | None) -> None:
    if df is None:
        return
    if df.empty:
        _compact_dataframe(df)
        return
    date_col = "install_date" if "install_date" in df.columns else df.columns[0]
    df_work = df.copy()
    df_work[date_col] = pd.to_datetime(df_work[date_col])
    df_nov = df_work.loc[(df_work[date_col] >= _NOV_START) & (df_work[date_col] < _NOV_END)].copy()
    value_cols = [c for c in df_nov.columns if c != date_col]
    if value_cols:
        _plotly_chart(_plotly_line(df_nov, date_col, value_cols))
    if df_nov.empty:
        st.info("Aucune ligne en novembre 2025 pour ce résultat.")
    _compact_dataframe(df_nov)


PanelKind = Literal["bar_cat", "bar_winrate_h", "metrics_c", "metrics_d", "line_nov"]


@dataclass(frozen=True)
class Panel:
    tab_label: str
    subheader: str
    sql_file: str
    kind: PanelKind
    caption: str | None = None


_PANELS: tuple[Panel, ...] = (
    Panel(
        "(a) Avg installs / day / country",
        "Average installs per day by country",
        "part3_a_avg_installs_per_day.sql",
        "bar_cat",
    ),
    Panel(
        "(b) Top 5 lowest win-rate levels",
        "Top 5 levels with lowest global win rate",
        "part3_b_top5_lowest_win_rate_levels.sql",
        "bar_winrate_h",
        "Barres **horizontales** : **taux de réussite (%)** en abscisse (X), **niveau** en ordonnée (Y). "
        "Le niveau le plus difficile (taux le plus bas) est en haut.",
    ),
    Panel(
        "(c) Win rate level 25 — 2 Nov",
        "Win rate of level 25 for users that installed on 2 Nov 2025",
        "part3_c_win_rate_level_25_nov2.sql",
        "metrics_c",
    ),
    Panel(
        "(d) D7 retention FR — 11 Nov",
        "Retention D7 for French users that installed on 11 Nov 2025",
        "part3_d_retention_d7_fr_nov11.sql",
        "metrics_d",
    ),
    Panel(
        "(e) Trailing 7d MA installs",
        "Trailing 7-day moving average of daily installs (November 2025)",
        "part3_e_trailing_7d_ma_installs.sql",
        "line_nov",
    ),
)


def _render_panel(con: duckdb.DuckDBPyConnection, panel: Panel) -> None:
    st.subheader(panel.subheader)
    if panel.caption:
        st.caption(panel.caption)

    df, sql = _run_analysis(con, panel.sql_file)
    k = panel.kind

    if k == "bar_cat" and df is not None and len(df.columns) >= 2:
        _plotly_chart(_plotly_bar_categories_metric(df, 0, 1))
    elif k == "bar_winrate_h" and df is not None and len(df.columns) >= 2:
        _plotly_chart(_plotly_bar_levels_winrate_horizontal(df))
    elif k == "metrics_c":
        _metrics_row_c(df)
    elif k == "metrics_d":
        _metrics_row_d(df)
    elif k == "line_nov":
        _tab_line_november(df)
        _sql_expander(sql)
        return

    if k != "line_nov" and df is not None:
        _compact_dataframe(df)
    _sql_expander(sql)


def main() -> None:
    st.set_page_config(page_title="Homa — Analytics dashboard", layout="wide")
    _inject_centered_layout_css()
    st.title("HOMA case study — analytics dashboard")
    st.caption(
        "SQL source: `dbt/analyses/part3_*.sql` (refs → "
        f"`{_dbt_schema()}.*`). Run `cd dbt && dbt run` if tables are missing."
    )

    con = _connect()
    if con is None:
        st.error(f"Database not found at `{_db_path()}`. Set HOMA_DUCKDB_PATH or run dbt.")
        st.stop()

    tabs = st.tabs([p.tab_label for p in _PANELS])
    for tab, panel in zip(tabs, _PANELS, strict=True):
        with tab:
            _render_panel(con, panel)


if __name__ == "__main__":
    main()
