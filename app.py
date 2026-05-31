import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(layout="wide", page_title="Implementation Lead Time", page_icon="📊")

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Page background */
  .stApp { background-color: #ffffff; }
  .block-container { padding: 1rem 1.5rem 0.5rem 1.5rem !important; max-width: 100% !important; }

  /* Hide Streamlit default header / footer */
  #MainMenu { visibility: hidden; }
  footer { visibility: hidden; }
  header { visibility: hidden; }

  /* KPI card */
  .kpi-card {
    background: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 4px;
    padding: 14px 18px 10px 18px;
    min-width: 120px;
    display: inline-block;
    margin-right: 6px;
    margin-bottom: 6px;
  }
  .kpi-value {
    font-size: 2.1rem;
    font-weight: 700;
    color: #000000;
    line-height: 1.1;
  }
  .kpi-label {
    font-size: 0.78rem;
    color: #666666;
    margin-top: 4px;
    font-weight: 400;
  }

  /* KPI row container */
  .kpi-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }

  /* Filter row */
  .filter-label {
    font-size: 0.7rem;
    color: #888888;
    margin-bottom: 1px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  /* In-Scope button style */
  .inscope-btn {
    background: #2d2d2d;
    color: #ffffff;
    border-radius: 14px;
    padding: 4px 12px;
    font-size: 0.75rem;
    font-weight: 600;
    display: inline-block;
    margin-bottom: 3px;
    white-space: nowrap;
  }

  /* Section title */
  .section-title {
    font-size: 0.88rem;
    font-weight: 600;
    color: #222222;
    margin-bottom: 6px;
    padding-bottom: 4px;
    border-bottom: 1px solid #e0e0e0;
  }

  /* Comparison table */
  .comp-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
  }
  .comp-table th {
    background: #f5f5f5;
    border-bottom: 1px solid #d9d9d9;
    padding: 5px 8px;
    text-align: left;
    font-weight: 600;
    color: #444444;
    white-space: nowrap;
  }
  .comp-table td {
    border-bottom: 1px solid #eeeeee;
    padding: 4px 8px;
    color: #222222;
    white-space: nowrap;
  }
  .comp-table tr:hover td { background: #f9f9f9; }
  .browse-link {
    color: #1155cc;
    text-decoration: underline;
    cursor: pointer;
    font-size: 0.76rem;
  }

  /* Divider between top and bottom sections */
  .section-divider {
    border: none;
    border-top: 1px solid #e0e0e0;
    margin: 10px 0 10px 0;
  }

  /* Streamlit selectbox tweaks */
  div[data-baseweb="select"] > div {
    font-size: 0.8rem !important;
    min-height: 30px !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Constants ────────────────────────────────────────────────────────────────
EXCEL_PATH = Path(__file__).parent / "QBR time in status.xlsx"
SCOPE_DATE = pd.Timestamp("2025-09-15")
DEBUG_PATH = Path(__file__).parent / "debug_output.csv"


# ── Helpers ──────────────────────────────────────────────────────────────────
def format_jira(hours: float) -> str:
    if pd.isna(hours) or hours <= 0:
        return ""
    total_minutes = int(hours * 60)
    d = total_minutes // (24 * 60)
    rem = total_minutes % (24 * 60)
    h = rem // 60
    m = rem % 60
    return f"{d}d {h}h {m}m"


def assign_quarter(dt: pd.Timestamp) -> str:
    if pd.isna(dt):
        return "Unknown"
    # All in-scope epics belong to 25Q4 per the dashboard definition
    if dt >= SCOPE_DATE:
        return "25Q4"
    y = dt.year % 100
    q = (dt.month - 1) // 3 + 1
    return f"{y:02d}Q{q}"


# ── Data loading & ILT calculation ───────────────────────────────────────────
@st.cache_data
def calculate_ilt(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df = df.sort_values(["key", "status_time"]).reset_index(drop=True)

    records = []
    for key, grp in df.groupby("key"):
        grp = grp.sort_values("status_time").reset_index(drop=True)
        impl_rows = grp[grp["status"] == "Implementation"]
        if impl_rows.empty:
            continue

        # "created" = first appearance in New status (= created column)
        created_date = grp["created"].iloc[0]
        in_scope = bool(created_date >= SCOPE_DATE)

        first_impl = impl_rows["status_time"].min()
        quarter = assign_quarter(first_impl)

        impl_hours = float(impl_rows["time_in_status"].sum())

        oh_rows = grp[
            (grp["status"] == "On Hold") & (grp["status_time"] >= first_impl)
        ]
        oh_hours = float(oh_rows["time_in_status"].sum())

        total_hours = impl_hours + oh_hours
        total_days = total_hours / 24

        notes = []
        if not grp[grp["status"] == "Canceled"].empty:
            notes.append("has Canceled rows")
        oh_before = grp[
            (grp["status"] == "On Hold") & (grp["status_time"] < first_impl)
        ]
        if not oh_before.empty:
            notes.append(
                f"excluded {len(oh_before)} On Hold row(s) before Implementation"
            )
        multi_impl = len(impl_rows) > 1
        if multi_impl:
            notes.append(f"{len(impl_rows)} Implementation stints summed")

        records.append(
            {
                "key": key,
                "created": created_date,
                "first_implementation_timestamp": first_impl,
                "in_scope_15_sep": in_scope,
                "quarter": quarter,
                "implementation_duration_hours": round(impl_hours, 4),
                "implementation_duration_days": round(impl_hours / 24, 4),
                "included_on_hold_duration_hours": round(oh_hours, 4),
                "included_on_hold_duration_days": round(oh_hours / 24, 4),
                "calculated_implementation_lead_time_hours": round(total_hours, 4),
                "calculated_implementation_lead_time_days": round(total_days, 4),
                "jira_display_value": format_jira(impl_hours),
                "included_status_rows": len(impl_rows) + len(oh_rows),
                "notes": "; ".join(notes),
            }
        )

    return pd.DataFrame(records)


# ── Load data ────────────────────────────────────────────────────────────────
df_all = calculate_ilt(str(EXCEL_PATH))

# Persist debug output (runs on first load / cache miss)
df_all.to_csv(DEBUG_PATH, index=False)

# ── Filter options ───────────────────────────────────────────────────────────
quarters_available = sorted(
    df_all[df_all["in_scope_15_sep"]]["quarter"].unique()
)
squads_available = ["All"]   # no Squad column in Excel
tribes_available = ["All"]   # no Tribe column in Excel

# ── Top-row layout: KPIs (left) + Filters (right) ───────────────────────────
top_left, top_right = st.columns([3, 2], gap="medium")

with top_right:
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    fcol1, fcol2, fcol3, fcol4 = st.columns([1, 1, 1, 1])

    with fcol1:
        st.markdown("<div class='filter-label'>Squad</div>", unsafe_allow_html=True)
        sel_squad = st.selectbox("Squad", squads_available, label_visibility="collapsed")

    with fcol2:
        st.markdown("<div class='filter-label'>Tribe</div>", unsafe_allow_html=True)
        sel_tribe = st.selectbox("Tribe", tribes_available, label_visibility="collapsed")

    with fcol3:
        st.markdown("<div class='filter-label'>Quarter</div>", unsafe_allow_html=True)
        default_q_idx = quarters_available.index("25Q4") if "25Q4" in quarters_available else 0
        sel_quarter = st.selectbox(
            "Quarter",
            quarters_available,
            index=default_q_idx,
            label_visibility="collapsed",
        )

    with fcol4:
        st.markdown(
            "<div class='inscope-btn'>In Scope (15 Sep+)</div>",
            unsafe_allow_html=True,
        )
        inscope_opts = ["All", "In Scope Only"]
        sel_inscope = st.selectbox("InScope", inscope_opts, label_visibility="collapsed")

# ── Apply filters ────────────────────────────────────────────────────────────
df_filtered = df_all.copy()

if sel_quarter != "All":
    df_filtered = df_filtered[df_filtered["quarter"] == sel_quarter]

if sel_inscope == "In Scope Only":
    df_filtered = df_filtered[df_filtered["in_scope_15_sep"]]

# KPIs / chart: when "In Scope Only" restrict to in-scope; "All" uses full quarter set
if sel_inscope == "In Scope Only":
    df_kpi = df_filtered[df_filtered["in_scope_15_sep"]].copy()
else:
    df_kpi = df_filtered.copy()
vals = df_kpi["calculated_implementation_lead_time_days"]

mean_val   = vals.mean()   if len(vals) > 0 else 0.0
median_val = vals.median() if len(vals) > 0 else 0.0
p50_val    = vals.quantile(0.50) if len(vals) > 0 else 0.0
p95_val    = vals.quantile(0.95) if len(vals) > 0 else 0.0

# ── KPI cards ────────────────────────────────────────────────────────────────
with top_left:
    st.markdown(
        f"""
        <div class='kpi-row'>
          <div class='kpi-card'>
            <div class='kpi-value'>{mean_val:.2f}</div>
            <div class='kpi-label'>Mean</div>
          </div>
          <div class='kpi-card'>
            <div class='kpi-value'>{median_val:.2f}</div>
            <div class='kpi-label'>Median</div>
          </div>
        </div>
        <div class='kpi-row'>
          <div class='kpi-card'>
            <div class='kpi-value'>{p50_val:.2f}</div>
            <div class='kpi-label'>P50</div>
          </div>
          <div class='kpi-card'>
            <div class='kpi-value'>{p95_val:.2f}</div>
            <div class='kpi-label'>P95</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Divider ──────────────────────────────────────────────────────────────────
st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

# ── Bottom row: Table (left) + Histogram (right) ─────────────────────────────
bot_left, bot_right = st.columns([5, 6], gap="medium")

# ── Comparison table ─────────────────────────────────────────────────────────
with bot_left:
    st.markdown(
        "<div class='section-title'>Implementation Lead Time Comparison</div>",
        unsafe_allow_html=True,
    )

    df_table = df_kpi.sort_values(
        "first_implementation_timestamp"
    )[["key", "calculated_implementation_lead_time_days", "jira_display_value"]].copy()

    rows_html = ""
    for _, row in df_table.iterrows():
        key = row["key"]
        calc = f"{row['calculated_implementation_lead_time_days']:.2f}"
        jira = row["jira_display_value"] if row["jira_display_value"] else ""
        rows_html += (
            f"<tr>"
            f"<td>{key}</td>"
            f"<td style='text-align:right'>{calc}</td>"
            f"<td>{jira}</td>"
            f"<td><span class='browse-link'>Browse ↗</span></td>"
            f"</tr>"
        )

    table_html = f"""
    <div style="height:420px; overflow-y:auto; border:1px solid #d9d9d9; border-radius:4px;">
      <table class='comp-table'>
        <thead>
          <tr>
            <th>Epics in scope</th>
            <th style='text-align:right'>Calculated</th>
            <th>Jira</th>
            <th>Browse Button</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)

# ── Histogram ────────────────────────────────────────────────────────────────
with bot_right:
    st.markdown(
        "<div class='section-title'>Count of Epics by ILT</div>",
        unsafe_allow_html=True,
    )

    if len(vals) > 0:
        bin_size = 5
        x_max = max(200, int(vals.max()) + 10)
        bins = list(range(0, x_max + bin_size, bin_size))

        counts, edges = np.histogram(vals.dropna().values, bins=bins)

        fig = go.Figure()

        # Histogram bars
        fig.add_trace(
            go.Bar(
                x=edges[:-1],
                y=counts,
                width=bin_size * 0.85,
                marker_color="#4472C4",
                marker_line_color="#4472C4",
                marker_line_width=0.5,
                name="Epics",
                hovertemplate="ILT: %{x}–%{customdata}d<br>Count: %{y}<extra></extra>",
                customdata=edges[1:],
            )
        )

        # P50 dashed line
        fig.add_vline(
            x=p50_val,
            line_dash="dash",
            line_color="#666666",
            line_width=1.5,
        )
        fig.add_annotation(
            x=p50_val,
            y=counts.max() * 1.05,
            text=f"P50: {int(round(p50_val))}",
            showarrow=False,
            font=dict(size=10, color="#444444"),
            xanchor="left",
            xshift=4,
        )

        # P95 dashed line
        fig.add_vline(
            x=p95_val,
            line_dash="dash",
            line_color="#666666",
            line_width=1.5,
        )
        fig.add_annotation(
            x=p95_val,
            y=counts.max() * 1.05,
            text=f"P95: {int(round(p95_val))}",
            showarrow=False,
            font=dict(size=10, color="#444444"),
            xanchor="left",
            xshift=4,
        )

        fig.update_layout(
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            margin=dict(l=30, r=20, t=20, b=40),
            xaxis=dict(
                title="Implementation Lead Time (days)",
                title_font=dict(size=11),
                tickfont=dict(size=10),
                range=[0, x_max],
                showgrid=True,
                gridcolor="#e8e8e8",
                gridwidth=1,
                zeroline=False,
            ),
            yaxis=dict(
                title="Count of Epics",
                title_font=dict(size=11),
                tickfont=dict(size=10),
                showgrid=True,
                gridcolor="#e8e8e8",
                gridwidth=1,
                zeroline=False,
            ),
            showlegend=False,
            height=420,
            bargap=0.1,
        )

        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No data to display for the selected filters.")
