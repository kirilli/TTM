import hashlib
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from calc import compute_metrics

st.set_page_config(layout="wide", page_title="Time Metrics Dashboard", page_icon="📊")

st.markdown("""
<style>
  .stApp { background-color: #ffffff; }
  .block-container { padding: 1rem 1.5rem 0.5rem 1.5rem !important; max-width: 100% !important; }
  #MainMenu, footer, header { visibility: hidden; }

  .dash-title {
    font-size: 1.1rem; font-weight: 700; color: #111; margin-bottom: 10px; letter-spacing: -0.01em;
  }

  .kpi-card {
    background: #ffffff; border: 1px solid #d9d9d9; border-radius: 4px;
    padding: 12px 18px 10px 18px; display: inline-block; margin-right: 8px; margin-bottom: 6px;
  }
  .kpi-value { font-size: 2rem; font-weight: 700; color: #000; line-height: 1.1; }
  .kpi-label { font-size: 0.75rem; color: #666; margin-top: 4px; }
  .kpi-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }

  .section-title {
    font-size: 0.85rem; font-weight: 600; color: #222; margin-bottom: 6px;
    padding-bottom: 4px; border-bottom: 1px solid #e0e0e0;
  }

  div[data-baseweb="select"] > div { font-size: 0.8rem !important; min-height: 32px !important; }
  .stDateInput input { font-size: 0.8rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────
EXCEL_PATH = Path(__file__).parent / "QBR time in status (NEW).xlsx"

METRICS = {
    "Discovery Cycle Time": "disc_ct_d",
    "Discovery Lead Time":  "disc_lt_d",
    "Delivery Cycle Time":  "del_ct_d",
    "Delivery Lead Time":   "del_lt_d",
    "Time to Market":       "ttm_d",
}


# ── Data ──────────────────────────────────────────────────────────────────────
def _calc_hash() -> str:
    calc_path = Path(__file__).parent / "calc.py"
    return hashlib.md5(calc_path.read_bytes()).hexdigest()[:8]

@st.cache_data
def load_data(path: str, calc_ver: str = "") -> pd.DataFrame:
    return compute_metrics(path)

df_all = load_data(str(EXCEL_PATH), calc_ver=_calc_hash())

all_tribes   = sorted(t for t in df_all["tribe"].unique() if t and t != "nan")
all_quarters = sorted(set(q for qs in df_all["quarters"] for q in qs))


# ── Filters ───────────────────────────────────────────────────────────────────
st.markdown("<div class='dash-title'>Time Metrics Dashboard</div>", unsafe_allow_html=True)

f1, f2, f3, f4, f5 = st.columns([3, 3, 2, 2, 3])
with f1:
    sel_tribes = st.multiselect("Tribe", all_tribes, placeholder="All tribes")
with f2:
    sel_quarters = st.multiselect("Quarter (Fix Version)", all_quarters, placeholder="All quarters")
with f3:
    sel_created_after = st.date_input("Created After", value=None)
with f4:
    sel_completed_after = st.date_input("Completed After", value=None)
with f5:
    sel_metric = st.selectbox("Metric", list(METRICS.keys()))


# ── Apply filters ─────────────────────────────────────────────────────────────
df = df_all.copy()
if sel_tribes:
    df = df[df["tribe"].isin(sel_tribes)]
if sel_quarters:
    sel_q_set = set(sel_quarters)
    df = df[df["quarters"].apply(lambda qs: bool(sel_q_set.intersection(qs)))]
if sel_created_after is not None:
    df = df[df["created"] > pd.Timestamp(sel_created_after)]
if sel_completed_after is not None:
    df = df[df["completed_date"] > pd.Timestamp(sel_completed_after)]

metric_col = METRICS[sel_metric]
vals = df[metric_col].dropna()
n = len(vals)

mean_v   = float(vals.mean())         if n > 0 else float("nan")
median_v = float(vals.median())       if n > 0 else float("nan")
p95_v    = float(vals.quantile(0.95)) if n > 0 else float("nan")

def fmt(v: float) -> str:
    return f"{v:.1f}" if not np.isnan(v) else "—"


# ── KPI Cards ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='kpi-row'>
  <div class='kpi-card'>
    <div class='kpi-value'>{fmt(mean_v)}</div>
    <div class='kpi-label'>Mean (days)</div>
  </div>
  <div class='kpi-card'>
    <div class='kpi-value'>{fmt(median_v)}</div>
    <div class='kpi-label'>Median / P50 (days)</div>
  </div>
  <div class='kpi-card'>
    <div class='kpi-value'>{fmt(p95_v)}</div>
    <div class='kpi-label'>P95 (days)</div>
  </div>
  <div class='kpi-card'>
    <div class='kpi-value'>{n}</div>
    <div class='kpi-label'>Epics</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    "<hr style='border:none;border-top:1px solid #e0e0e0;margin:6px 0 10px 0'>",
    unsafe_allow_html=True,
)


# ── Table | Histogram ─────────────────────────────────────────────────────────
tbl_col, hist_col = st.columns([5, 6], gap="medium")

# ── Epic table ────────────────────────────────────────────────────────────────
with tbl_col:
    st.markdown("<div class='section-title'>Epic Details</div>", unsafe_allow_html=True)

    df_table = (
        df[["key", "created", "disc_ct_d", "disc_lt_d", "del_ct_d", "del_lt_d", "ttm_d"]]
        .sort_values("key")
        .reset_index(drop=True)
    )

    st.dataframe(
        df_table,
        column_config={
            "key":       st.column_config.TextColumn("Epic Key", width="small"),
            "created":   st.column_config.DateColumn("Created", format="YYYY-MM-DD", width="small"),
            "disc_ct_d": st.column_config.NumberColumn("Discovery CT", format="%.1f", help="Discovery Cycle Time (days)"),
            "disc_lt_d": st.column_config.NumberColumn("Discovery LT", format="%.1f", help="Discovery Lead Time (days)"),
            "del_ct_d":  st.column_config.NumberColumn("Delivery CT",  format="%.1f", help="Delivery Cycle Time (days)"),
            "del_lt_d":  st.column_config.NumberColumn("Delivery LT",  format="%.1f", help="Delivery Lead Time (days)"),
            "ttm_d":     st.column_config.NumberColumn("TTM",          format="%.1f", help="Time to Market (days)"),
        },
        use_container_width=True,
        hide_index=True,
        height=460,
    )

# ── Histogram ─────────────────────────────────────────────────────────────────
with hist_col:
    st.markdown(
        f"<div class='section-title'>Distribution — {sel_metric}</div>",
        unsafe_allow_html=True,
    )

    if n > 0:
        p50_v = median_v
        x_max = max(int(np.nanpercentile(vals, 99)) + 10, 30)
        bin_size = max(1, x_max // 35)
        bins = list(range(0, x_max + bin_size, bin_size))
        counts, edges = np.histogram(vals.values, bins=bins)
        y_max = int(counts.max()) if counts.max() > 0 else 1

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=edges[:-1],
            y=counts,
            width=bin_size * 0.85,
            marker_color="#4472C4",
            marker_line_color="#4472C4",
            marker_line_width=0.4,
            hovertemplate=f"{sel_metric}: %{{x}}–%{{customdata}}d<br>Epics: %{{y}}<extra></extra>",
            customdata=edges[1:],
        ))

        for pval, plabel in [(p50_v, "P50"), (p95_v, "P95")]:
            if not np.isnan(pval):
                fig.add_vline(x=pval, line_dash="dash", line_color="#555", line_width=1.5)
                fig.add_annotation(
                    x=pval, y=y_max * 1.08,
                    text=f"{plabel}: {pval:.0f}d",
                    showarrow=False,
                    font=dict(size=10, color="#333"),
                    xanchor="left",
                    xshift=5,
                )

        fig.update_layout(
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            margin=dict(l=30, r=20, t=24, b=40),
            xaxis=dict(
                title=f"{sel_metric} (days)",
                title_font=dict(size=11),
                tickfont=dict(size=10),
                range=[0, x_max],
                showgrid=True,
                gridcolor="#ebebeb",
                zeroline=False,
            ),
            yaxis=dict(
                title="Count of Epics",
                title_font=dict(size=11),
                tickfont=dict(size=10),
                showgrid=True,
                gridcolor="#ebebeb",
                zeroline=False,
            ),
            showlegend=False,
            height=460,
            bargap=0.1,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No data for the selected filters.")
