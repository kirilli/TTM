"""
Agile CoE Time Metrics — local dashboard
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime

st.set_page_config(
    layout="wide",
    page_title="Agile CoE Time Metrics",
    page_icon="📊",
    initial_sidebar_state="collapsed",
)

# ── Imports from calculation engine ──────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent))
from calc import compute_all, data_quality, format_jira, format_jira_full

# ── Constants ─────────────────────────────────────────────────────────────────
EXCEL_PATH = Path(__file__).parent / "QBR time in status (NEW).xlsx"

METRICS = [
    {"name": "Discovery Cycle Time",  "icon": "⏱",  "short": "DCT"},
    {"name": "Discovery Lead Time",   "icon": "⏱",  "short": "DLT"},
    {"name": "Delivery Cycle Time",   "icon": "🚚", "short": "DCyT"},
    {"name": "Delivery Lead Time",    "icon": "🚚", "short": "DLyT"},
    {"name": "Time to Market",        "icon": "🎯", "short": "TTM"},
]
METRIC_NAMES = [m["name"] for m in METRICS]
DEFAULT_METRIC = "Delivery Cycle Time"

FORMULAS = {
    "Discovery Cycle Time": {
        "eq":   "Discovery Cycle Time = T<sub>exit</sub> Discovery − T<sub>enter</sub> Discovery",
        "note": "Cycle Time metrics exclude On Hold periods.",
        "more": "Lead Time metrics include relevant On Hold periods.",
    },
    "Discovery Lead Time": {
        "eq":   "Discovery Lead Time = Discovery Cycle Time + On Hold after entering Discovery",
        "note": "Lead Time metrics include relevant On Hold periods.",
        "more": "Cycle Time metrics exclude On Hold periods.",
    },
    "Delivery Cycle Time": {
        "eq":   "Delivery Cycle Time = T<sub>exit</sub> Implementation − T<sub>enter</sub> Discovery Completed",
        "note": "Cycle Time metrics exclude On Hold periods.",
        "more": "Lead Time metrics include relevant On Hold periods.",
    },
    "Delivery Lead Time": {
        "eq":   "Delivery Lead Time = Delivery Cycle Time + On Hold after Discovery Completed",
        "note": "Lead Time metrics include relevant On Hold periods.",
        "more": "Cycle Time metrics exclude On Hold periods.",
    },
    "Time to Market": {
        "eq":   "Time to Market = T<sub>exit</sub> Implementation − T<sub>enter</sub> Discovery + On Hold after Discovery",
        "note": "TTM includes Discovery, Delivery, Implementation and relevant On Hold periods.",
        "more": "",
    },
}

# Old-screenshot validation targets (ILT proxy)
OLD_KPI_TARGETS = {"mean": 49.47, "median": 43.01, "p50": 44.00, "p95": 139.00}
OLD_ROW_TARGETS = {
    "QBR-1990": (159.80, "85d 19h 32m"), "QBR-2555": (19.12, "19d 2h 51m"),
    "QBR-2558": (70.92,  None),           "QBR-2008": (98.00,  None),
    "QBR-2850": (21.38,  "21d 9h 6m"),   "QBR-2874": (1.01,   "1d 0h 12m"),
    "QBR-2875": (1.04,   "1d 0h 57m"),   "QBR-2107": (110.11, "110d 2h 35m"),
    "QBR-2675": (66.83,  "66d 20h 0m"),
}

# ── Session state ─────────────────────────────────────────────────────────────
if "metric" not in st.session_state:
    st.session_state.metric = DEFAULT_METRIC

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ----- global ----- */
  .stApp { background: #f3f3f3 !important; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  #MainMenu, footer, header { visibility: hidden; }
  section[data-testid="stSidebar"] { display: none; }

  /* ----- outer shell ----- */
  .outer { background: #ffffff; margin: 0; padding: 0; }

  /* ----- app header ----- */
  .app-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    padding: 10px 20px 8px; border-bottom: 1px solid #e0e0e0;
    background: #ffffff;
  }
  .app-title { font-size: 1.35rem; font-weight: 700; color: #1a1a1a; margin: 0; line-height: 1.2; }
  .app-subtitle { font-size: 0.78rem; color: #666; margin: 2px 0 0; }
  .hdr-right { text-align: right; }
  .data-ts { font-size: 0.72rem; color: #888; }
  .clear-filters { font-size: 0.72rem; color: #0078d4; cursor: pointer; text-decoration: underline; margin-top: 3px; display: block; }

  /* ----- metric tabs ----- */
  .tab-bar { display: flex; border-bottom: 2px solid #e0e0e0; background: #fafafa; }
  .tab-item {
    flex: 1; padding: 9px 6px 7px; text-align: center; cursor: pointer;
    border: 1px solid #e0e0e0; border-bottom: none;
    font-size: 0.77rem; color: #555; background: #fafafa;
    user-select: none; line-height: 1.3;
  }
  .tab-item.sel {
    background: #0078d4; color: #fff; font-weight: 600;
    border-color: #0078d4; border-bottom-color: #0078d4;
  }
  .tab-item:not(.sel):hover { background: #f0f0f0; }
  .tab-icon { font-size: 1.1rem; display: block; margin-bottom: 1px; }

  /* ----- body ----- */
  .body-wrap { display: flex; gap: 0; padding: 0; background: #ffffff; }
  .left-col  { flex: 0 0 47%; padding: 12px 14px 8px; border-right: 1px solid #e8e8e8; }
  .right-col { flex: 1 1 53%; padding: 10px 14px 8px; }

  /* ----- KPI cards ----- */
  .kpi-row { display: flex; gap: 8px; margin-bottom: 10px; }
  .kpi-card {
    flex: 1; background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
    padding: 10px 10px 8px; display: flex; align-items: flex-start; gap: 8px;
  }
  .kpi-circle {
    width: 38px; height: 38px; border-radius: 50%; border: 2.5px solid #0078d4;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; font-size: 0.78rem; font-weight: 700; color: #0078d4;
  }
  .kpi-circle.p50-c  { background: #0078d4; color: #fff; border-color: #0078d4; }
  .kpi-circle.p95-c  { background: #c83200; color: #fff; border-color: #c83200; }
  .kpi-circle.cnt-c  { border-color: #107c10; color: #107c10; }
  .kpi-circle.mean-c { border-color: #0078d4; color: #0078d4; }
  .kpi-num   { font-size: 1.9rem; font-weight: 700; color: #1a1a1a; line-height: 1.05; }
  .kpi-lbl   { font-size: 0.68rem; color: #777; margin-top: 2px; }

  /* ----- formula panel ----- */
  .formula-box {
    background: #eef4fb; border: 1px solid #bad4f5; border-radius: 6px;
    padding: 9px 13px; margin-bottom: 10px; font-size: 0.8rem;
  }
  .formula-info { display: flex; gap: 8px; align-items: flex-start; }
  .formula-icon { font-size: 1.1rem; flex-shrink: 0; color: #0078d4; margin-top: 1px; }
  .formula-main { color: #1a1a1a; font-weight: 500; margin: 0 0 3px; }
  .formula-note { color: #555; margin: 0 0 2px; font-size: 0.76rem; }
  .formula-more { color: #555; margin: 0; font-size: 0.76rem; }
  .formula-link { color: #0078d4; text-decoration: underline; font-size: 0.74rem; margin-top: 5px; display: inline-block; }

  /* ----- section title ----- */
  .sec-title { font-size: 0.9rem; font-weight: 700; color: #1a1a1a; margin-bottom: 6px; }

  /* ----- comparison table ----- */
  .cmp-wrap { overflow-y: auto; max-height: 390px; border: 1px solid #e0e0e0; border-radius: 4px; }
  .cmp-table { width: 100%; border-collapse: collapse; font-size: 0.77rem; }
  .cmp-table th {
    background: #f5f5f5; padding: 6px 8px; font-weight: 600; color: #444;
    border-bottom: 1.5px solid #d9d9d9; white-space: nowrap; position: sticky; top: 0;
    text-align: left;
  }
  .cmp-table th.r { text-align: right; }
  .cmp-table td { padding: 4px 8px; border-bottom: 1px solid #f0f0f0; color: #222; }
  .cmp-table td.r { text-align: right; }
  .cmp-table tr:hover td { background: #fafafa; }
  .b-match { background:#e6f4ea; color:#137333; border-radius:10px; padding:2px 7px; font-size:0.7rem; font-weight:600; white-space:nowrap; }
  .b-minor { background:#fff8e1; color:#b06b00; border-radius:10px; padding:2px 7px; font-size:0.7rem; font-weight:600; white-space:nowrap; }
  .b-sig   { background:#fce8e6; color:#c5221f; border-radius:10px; padding:2px 7px; font-size:0.7rem; font-weight:600; white-space:nowrap; }
  .b-miss  { background:#e8eaf6; color:#3949ab; border-radius:10px; padding:2px 7px; font-size:0.7rem; font-weight:600; white-space:nowrap; }
  .b-excl  { background:#f5f5f5; color:#757575; border-radius:10px; padding:2px 7px; font-size:0.7rem; font-weight:600; white-space:nowrap; }
  .browse-a { color:#0078d4; text-decoration:underline; font-size:0.75rem; }

  /* ----- filter area ----- */
  .filter-row { display: flex; gap: 10px; margin-bottom: 10px; align-items: flex-end; }
  .filter-group { flex: 1; }
  .filter-lbl { font-size: 0.67rem; color: #888; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 1px; font-weight: 500; }
  .inscope-pill { background:#1a1a1a; color:#fff; border-radius:14px; padding:3px 10px; font-size:0.7rem; font-weight:600; display:inline-block; margin-bottom:2px; }

  /* ----- data quality bar ----- */
  .dq-bar { display: flex; gap: 10px; padding: 10px 14px; border-top: 1px solid #e0e0e0; background: #fafafa; }
  .dq-card {
    flex: 1; background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
    padding: 8px 12px; display: flex; align-items: center; gap: 10px;
  }
  .dq-ico { font-size: 1.4rem; }
  .dq-num { font-size: 1.35rem; font-weight: 700; color: #1a1a1a; line-height: 1; }
  .dq-lbl { font-size: 0.7rem; color: #666; margin-top: 1px; }
  .dq-good { color: #107c10 !important; }
  .dq-warn { color: #b06b00 !important; }
  .dq-issue { color: #c5221f !important; }

  /* ----- Streamlit widget tweaks ----- */
  div[data-baseweb="select"] > div { font-size: 0.8rem !important; min-height: 30px !important; }
  .stButton > button { border-radius: 3px !important; font-size: 0.78rem !important; }
  div[data-testid="stExpander"] { border: 1px solid #e0e0e0 !important; border-radius: 4px; margin: 8px 14px; }
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading Excel and calculating metrics…")
def _load(path: str) -> dict:
    return compute_all(path)

all_data = _load(str(EXCEL_PATH))

# ── Derive filter options directly from raw Excel (fast, no cache dependency) ─
@st.cache_data(show_spinner=False)
def _load_raw(path: str) -> pd.DataFrame:
    return pd.read_excel(path)

_raw = _load_raw(str(EXCEL_PATH))

_fv_set = set()
for _val in _raw["fix_versions"].dropna():
    for _v in str(_val).split(","):
        _s = _v.strip()
        if _s and _s != "nan":
            _fv_set.add(_s)
_quarters_all = sorted(_fv_set, reverse=True)
if not _quarters_all or "25Q4" not in _quarters_all:
    _quarters_all = ["25Q4"] + _quarters_all

_tribes_all = sorted(set(
    str(t).strip() for t in _raw["tribe"].dropna()
    if str(t).strip() and str(t).strip() != "nan"
))
_squads_all = sorted(set(
    str(s).strip() for s in _raw["squad"].dropna()
    if str(s).strip() and str(s).strip() != "nan"
))

# ─────────────────────────────────────────────────────────────────────────────
# ── APP HEADER
# ─────────────────────────────────────────────────────────────────────────────
data_ts = all_data["ILT Proxy"]["first_implementation_timestamp"].dropna().max()
if pd.notna(data_ts):
    ts_str = data_ts.strftime("%d %b %Y").lstrip("0")
else:
    ts_str = "—"

st.markdown(f"""
<div class="app-header">
  <div>
    <div class="app-title">📊 Agile CoE Time Metrics</div>
    <div class="app-subtitle">Cycle Time, Lead Time &amp; Time to Market</div>
  </div>
  <div class="hdr-right">
    <div class="data-ts">Data as of: {ts_str} &nbsp; 🔄</div>
    <a class="clear-filters" href="#">Clear filters &#9698;</a>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# ── METRIC TAB BAR  (HTML visual) + hidden Streamlit buttons
# ─────────────────────────────────────────────────────────────────────────────
sel_metric = st.session_state.metric

tab_html = '<div class="tab-bar">'
for m in METRICS:
    cls = "tab-item sel" if m["name"] == sel_metric else "tab-item"
    tab_html += f'<div class="{cls}"><span class="tab-icon">{m["icon"]}</span>{m["name"]}</div>'
tab_html += "</div>"
st.markdown(tab_html, unsafe_allow_html=True)

# Actual clickable buttons (low-height row below the visual tabs)
_bcols = st.columns(5)
for _c, _m in zip(_bcols, METRICS):
    with _c:
        _label = "▶ " + _m["short"] if _m["name"] == sel_metric else _m["short"]
        if st.button(_label, key=f"_tab_{_m['short']}", use_container_width=True,
                     help=_m["name"],
                     type="primary" if _m["name"] == sel_metric else "secondary"):
            st.session_state.metric = _m["name"]
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# ── MAIN CONTENT:  left col  |  right col
# ─────────────────────────────────────────────────────────────────────────────
main_left, main_right = st.columns([47, 53], gap="small")

# ─── RIGHT COL: filters + histogram ──────────────────────────────────────────
with main_right:
    # Filters
    f1, f2, f3, f4 = st.columns([1, 1, 1, 1.3])
    with f1:
        st.markdown("<div class='filter-lbl'>Squad</div>", unsafe_allow_html=True)
        sel_squad = st.selectbox("Squad", ["All"] + _squads_all, label_visibility="collapsed")
    with f2:
        st.markdown("<div class='filter-lbl'>Tribe</div>", unsafe_allow_html=True)
        sel_tribe = st.selectbox("Tribe", ["All"] + _tribes_all, label_visibility="collapsed")
    with f3:
        st.markdown("<div class='filter-lbl'>Quarter</div>", unsafe_allow_html=True)
        _q_idx = _quarters_all.index("25Q4") if "25Q4" in _quarters_all else 0
        sel_quarter = st.selectbox("Quarter", ["All"] + _quarters_all,
                                   index=_q_idx + 1,
                                   label_visibility="collapsed")
    with f4:
        st.markdown("<div class='inscope-pill'>In Scope (15 Sep+)</div>", unsafe_allow_html=True)
        sel_inscope = st.selectbox("InScope", ["All", "Yes", "No"],
                                   label_visibility="collapsed")

    # ── Apply filters ─────────────────────────────────────────────────────────
    def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
        if sel_quarter != "All" and "fix_versions" in df.columns:
            df = df[df["fix_versions"].fillna("").apply(
                lambda x: sel_quarter in [v.strip() for v in str(x).split(",")]
            )]
        if sel_tribe != "All" and "tribe" in df.columns:
            df = df[df["tribe"].fillna("").str.strip() == sel_tribe]
        if sel_squad != "All" and "squad" in df.columns:
            df = df[df["squad"].fillna("").str.strip() == sel_squad]
        return df

    _total = len(all_data[sel_metric])
    df_metric = _apply_filters(all_data[sel_metric].copy())
    if sel_inscope == "Yes":
        df_metric = df_metric[df_metric["in_scope_15_sep"]]
    elif sel_inscope == "No":
        df_metric = df_metric[~df_metric["in_scope_15_sep"]]

    # KPI base = always in-scope + calculable (filters: quarter/tribe/squad for scope)
    df_kpi = _apply_filters(all_data[sel_metric].copy())
    df_kpi = df_kpi[df_kpi["in_scope_15_sep"] & df_kpi["calculated_metric_days"].notna()]

    st.caption(f"cols: {'tribe' in all_data[sel_metric].columns} | total: {_total} → filtered: {len(df_metric)} | kpi: {len(df_kpi)}")

    vals = df_kpi["calculated_metric_days"]
    mean_v   = vals.mean()    if len(vals) > 0 else np.nan
    med_v    = vals.median()  if len(vals) > 0 else np.nan
    p50_v    = vals.quantile(0.50) if len(vals) > 0 else np.nan
    p95_v    = vals.quantile(0.95) if len(vals) > 0 else np.nan
    count_v  = len(vals)

    # ── Histogram ────────────────────────────────────────────────────────────
    st.markdown(f"<div class='sec-title'>Count of Epics by {sel_metric}</div>",
                unsafe_allow_html=True)

    if len(vals) > 0:
        bin_sz = 5
        x_max  = max(160, int(np.ceil(vals.max() / bin_sz) * bin_sz) + bin_sz)
        bins   = list(range(0, x_max + bin_sz, bin_sz))
        counts, edges = np.histogram(vals.dropna().values, bins=bins)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=edges[:-1], y=counts,
            width=bin_sz * 0.82,
            marker_color="#4472C4", marker_line_color="#4472C4", marker_line_width=0.4,
            hovertemplate="%{x:.0f}–%{customdata:.0f}d: %{y} epics<extra></extra>",
            customdata=edges[1:],
        ))

        for val, label, xanchor in [
            (p50_v, f"P50: {p50_v:.1f}" if not np.isnan(p50_v) else "", "left"),
            (p95_v, f"P95: {p95_v:.1f}" if not np.isnan(p95_v) else "", "left"),
        ]:
            if not np.isnan(val):
                fig.add_vline(x=val, line_dash="dash", line_color="#666", line_width=1.5)
                fig.add_annotation(
                    x=val, y=counts.max() * 1.08,
                    text=label, showarrow=False,
                    font=dict(size=10, color="#444"),
                    xanchor=xanchor, xshift=5,
                )

        fig.update_layout(
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            margin=dict(l=30, r=10, t=18, b=40),
            xaxis=dict(
                title="Days", title_font=dict(size=10), tickfont=dict(size=9),
                range=[0, x_max], showgrid=True, gridcolor="#eeeeee", zeroline=False,
            ),
            yaxis=dict(
                title="Count of Epics", title_font=dict(size=10), tickfont=dict(size=9),
                showgrid=True, gridcolor="#eeeeee", zeroline=False,
            ),
            showlegend=False, height=390, bargap=0.08,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No calculable epics for this metric with current filters.")


# ─── LEFT COL: KPIs + formula + table ────────────────────────────────────────
with main_left:
    # ── KPI cards ─────────────────────────────────────────────────────────────
    def _fmt(v, decimals=1):
        return f"{v:.{decimals}f}" if not np.isnan(v) else "—"

    kpi_html = (
        '<div class="kpi-row">'
        '<div class="kpi-card"><div class="kpi-circle mean-c">≈</div>'
        f'<div><div class="kpi-num">{_fmt(mean_v,1)}</div><div class="kpi-lbl">Mean (days)</div></div></div>'
        '<div class="kpi-card"><div class="kpi-circle p50-c">50</div>'
        f'<div><div class="kpi-num">{_fmt(med_v,1)}</div><div class="kpi-lbl">Median / P50 (days)</div></div></div>'
        '<div class="kpi-card"><div class="kpi-circle p95-c">95</div>'
        f'<div><div class="kpi-num">{_fmt(p95_v,1)}</div><div class="kpi-lbl">P95 (days)</div></div></div>'
        '<div class="kpi-card"><div class="kpi-circle cnt-c">≡</div>'
        f'<div><div class="kpi-num">{count_v}</div><div class="kpi-lbl">Epic Count</div></div></div>'
        '</div>'
    )
    st.markdown(kpi_html, unsafe_allow_html=True)

    # ── Formula panel ──────────────────────────────────────────────────────────
    f = FORMULAS[sel_metric]
    _more = f'<p class="formula-more">{f["more"]}</p>' if f["more"] else ""
    formula_html = (
        '<div class="formula-box">'
        '<div class="formula-info">'
        '<div class="formula-icon">ℹ️</div>'
        f'<div><p class="formula-main">{f["eq"]}</p>'
        f'<p class="formula-note">{f["note"]}</p>'
        f'{_more}</div></div>'
        '<a class="formula-link" href="#">View all metric definitions ↗</a>'
        '</div>'
    )
    st.markdown(formula_html, unsafe_allow_html=True)

    # ── Comparison table ───────────────────────────────────────────────────────
    st.markdown("<div class='sec-title'>Metric Comparison</div>", unsafe_allow_html=True)

    # Table rows: all epics in df_metric that have a calculable value (or show excluded)
    df_table = df_metric.sort_values("key")

    BADGE = {
        "Match":               '<span class="b-match">✓ Match</span>',
        "Minor difference":    '<span class="b-minor">⚠ Minor diff</span>',
        "Significant difference": '<span class="b-sig">✕ Sig diff</span>',
        "Missing Jira value":  '<span class="b-miss">? No Jira</span>',
        "Missing transition":  '<span class="b-excl">– Missing</span>',
        "Out of scope":        '<span class="b-excl">○ Out scope</span>',
    }

    rows_html = ""
    for _, row in df_table.iterrows():
        key = row["key"]
        calc = f"{row['calculated_metric_days']:.2f}" if pd.notna(row["calculated_metric_days"]) else "—"
        jira = row["jira_display_value"] or "—"
        delta_raw = row["delta_days"]
        delta = f"{delta_raw:+.1f}" if pd.notna(delta_raw) else "—"
        vstatus = row["validation_status"]
        badge = BADGE.get(vstatus, f'<span class="b-excl">{vstatus}</span>')
        rows_html += (
            f"<tr>"
            f"<td>{key}</td>"
            f"<td class='r'>{calc}</td>"
            f"<td>{jira}</td>"
            f"<td class='r'>{delta}</td>"
            f"<td>{badge}</td>"
            f"<td><a class='browse-a'>Browse ↗</a></td>"
            f"</tr>"
        )

    table_html = (
        '<div class="cmp-wrap"><table class="cmp-table"><thead><tr>'
        '<th>Epic Key</th><th class="r">Calculated (days)</th><th>Jira (days)</th>'
        '<th class="r">Delta (days) &#x24D8;</th><th>Status</th><th>Browse</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# ── DATA QUALITY BAR
# ─────────────────────────────────────────────────────────────────────────────
dq = data_quality(df_kpi, sel_metric)
q_cls = {"Good": "dq-good", "Warning": "dq-warn", "Issue": "dq-issue"}.get(dq["quality"], "dq-good")

dq_html = (
    '<div class="dq-bar">'
    '<div class="dq-card"><div class="dq-ico">👥</div>'
    f'<div><div class="dq-num">{dq["epics_in_scope"]}</div><div class="dq-lbl">Epics in scope</div></div></div>'
    '<div class="dq-card"><div class="dq-ico">❓</div>'
    f'<div><div class="dq-num">{dq["missing_jira"]}</div><div class="dq-lbl">Missing Jira value</div></div></div>'
    '<div class="dq-card"><div class="dq-ico">🔍</div>'
    f'<div><div class="dq-num">{dq["excluded"]}</div><div class="dq-lbl">Excluded</div></div></div>'
    '<div class="dq-card"><div class="dq-ico">🗄</div>'
    f'<div><div class="dq-num {q_cls}">{dq["quality"]}</div><div class="dq-lbl">Data quality</div></div></div>'
    '</div>'
)
st.markdown(dq_html, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# ── DEBUG VIEW
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("🐛 Debug View — " + sel_metric, expanded=False):
    st.markdown("#### Metric debug table")

    df_debug = _apply_filters(all_data[sel_metric].copy())

    debug_cols = [
        "key", "tribe", "squad", "fix_versions", "in_scope_15_sep", "quarter",
        "first_implementation_timestamp", "metric_start_timestamp",
        "first_discovery_timestamp", "first_discovery_completed_timestamp",
        "first_delivery_committed_timestamp", "implementation_exit_timestamp",
        "active_status_duration_hours", "included_on_hold_duration_hours",
        "calculated_metric_hours", "calculated_metric_days",
        "jira_comparison_hours", "jira_display_value", "delta_days",
        "validation_status", "included_status_rows", "notes",
    ]
    debug_show = [c for c in debug_cols if c in df_debug.columns]
    st.dataframe(df_debug[debug_show], use_container_width=True, height=300)

    # CSV download
    csv_bytes = df_debug[debug_show].to_csv(index=False).encode()
    st.download_button(
        label=f"⬇ Download debug CSV ({sel_metric})",
        data=csv_bytes,
        file_name=f"debug_{sel_metric.replace(' ', '_').lower()}.csv",
        mime="text/csv",
    )

    # ── ILT Proxy validation (old screenshot targets) ───────────────────────
    st.markdown("---")
    st.markdown("#### ILT Proxy validation (old screenshot targets — 2025 proxy)")

    proxy_df = all_data["ILT Proxy"]
    inscope_proxy = proxy_df[proxy_df["in_scope_15_sep"] & proxy_df["calculated_metric_days"].notna()]
    pv = inscope_proxy["calculated_metric_days"]

    kpi_rows = []
    for kpi_name, target_val, calc_val in [
        ("Mean",   OLD_KPI_TARGETS["mean"],   pv.mean()),
        ("Median", OLD_KPI_TARGETS["median"], pv.median()),
        ("P50",    OLD_KPI_TARGETS["p50"],    pv.quantile(0.5)),
        ("P95",    OLD_KPI_TARGETS["p95"],    pv.quantile(0.95)),
    ]:
        diff = calc_val - target_val
        match = "✓ Close" if abs(diff) < 8 else "✗ Differ"
        kpi_rows.append({"KPI": kpi_name, "Target": target_val, "Calculated": round(calc_val, 2),
                         "Difference": round(diff, 2), "Result": match})
    st.markdown("**KPI targets (old screenshot) vs current Excel data:**")
    st.dataframe(pd.DataFrame(kpi_rows), use_container_width=True, hide_index=True)

    st.markdown("**Per-epic targets:**")
    epic_rows = []
    for key, (target_calc, target_jira) in OLD_ROW_TARGETS.items():
        row = proxy_df[proxy_df["key"] == key]
        if row.empty:
            epic_rows.append({"Key": key, "Target calc": target_calc, "Target Jira": target_jira or "—",
                               "Actual calc": "—", "Actual Jira": "—", "Diff": "—", "Match": "✗ Not found"})
            continue
        r = row.iloc[0]
        actual_d = r["calculated_metric_days"]
        actual_j = format_jira_full(r["active_status_duration_hours"]) if pd.notna(r["active_status_duration_hours"]) else "—"
        diff_d = round(actual_d - target_calc, 2) if pd.notna(actual_d) else None
        ok = "✓ Match" if diff_d is not None and abs(diff_d) < 1 else "≈ Close" if diff_d is not None and abs(diff_d) < 10 else "✗ Differ"
        epic_rows.append({
            "Key": key, "Target calc": target_calc, "Target Jira": target_jira or "—",
            "Actual calc": round(actual_d, 2) if pd.notna(actual_d) else "—",
            "Actual Jira": actual_j, "Diff": diff_d if diff_d is not None else "—",
            "Match": ok,
        })
    st.dataframe(pd.DataFrame(epic_rows), use_container_width=True, hide_index=True)

    st.markdown("""
**Why ILT Proxy values differ from screenshot targets:**
The Excel snapshot is from ~May 2026; the old screenshot was captured ~March 2026.
`time_in_status` is a running counter, so epics still in Implementation or On Hold
have accumulated additional hours. This inflates ILT values for ongoing epics
(most notably QBR-1990 and QBR-2558). Epics that completed before March 2026 match exactly.
""")
