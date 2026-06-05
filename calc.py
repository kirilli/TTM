"""
Agile CoE Time Metrics — calculation engine
"""
import pandas as pd
import numpy as np
from pathlib import Path

SCOPE_DATE = pd.Timestamp("2025-09-15")

DISC       = "discovery"
DISC_COMP  = "discovery completed"
DEL_COMMIT = "delivery committed"
IMPL       = "implementation"
ON_HOLD    = "on hold"

DELIVERY_ACTIVE = {DISC_COMP, DEL_COMMIT, IMPL}
TTM_ACTIVE      = {DISC, DISC_COMP, DEL_COMMIT, IMPL}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _first(grp: pd.DataFrame, statuses: set) -> pd.Timestamp:
    rows = grp[grp["sn"].isin(statuses)]
    return rows["status_time"].min() if not rows.empty else pd.NaT


def _sum_h(grp: pd.DataFrame, statuses: set) -> float:
    return float(grp[grp["sn"].isin(statuses)]["time_in_status"].sum())


def _oh_after(grp: pd.DataFrame, start: pd.Timestamp) -> float:
    """Sum On Hold time_in_status for all On Hold rows starting >= start."""
    if pd.isna(start):
        return 0.0
    return float(grp[(grp["sn"] == ON_HOLD) & (grp["status_time"] >= start)]["time_in_status"].sum())


def _oh_between(grp: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Sum On Hold time_in_status where status_time in [start, end)."""
    if pd.isna(start):
        return 0.0
    mask = (grp["sn"] == ON_HOLD) & (grp["status_time"] >= start)
    if not pd.isna(end):
        mask &= grp["status_time"] < end
    return float(grp[mask]["time_in_status"].sum())


def _impl_exit(grp: pd.DataFrame) -> pd.Timestamp:
    """Timestamp when epic left the last Implementation stint (or estimated exit)."""
    impl = grp[grp["sn"] == IMPL].sort_values("status_time")
    if impl.empty:
        return pd.NaT
    last = impl.iloc[-1]
    after = grp[grp["status_time"] > last["status_time"]]
    if not after.empty:
        return after["status_time"].iloc[0]
    # Still active — estimate from time_in_status
    return last["status_time"] + pd.Timedelta(hours=float(last["time_in_status"]))


def _delivery_start(grp: pd.DataFrame) -> pd.Timestamp:
    """Earliest of Discovery completed / Delivery committed."""
    return _first(grp, {DISC_COMP, DEL_COMMIT})


def _assign_quarter(dt: pd.Timestamp) -> str:
    if pd.isna(dt):
        return "Unknown"
    if dt >= SCOPE_DATE:
        return "25Q4"
    y = dt.year % 100
    q = (dt.month - 1) // 3 + 1
    return f"{y:02d}Q{q}"


def format_jira(hours: float) -> str:
    if pd.isna(hours) or hours <= 0:
        return ""
    total_m = int(hours * 60)
    d = total_m // (24 * 60)
    rem = total_m % (24 * 60)
    h = rem // 60
    return f"{d}d {h}h"


def format_jira_full(hours: float) -> str:
    """Xd Yh Zm format (for ILT proxy validation)."""
    if pd.isna(hours) or hours <= 0:
        return ""
    total_m = int(hours * 60)
    d = total_m // (24 * 60)
    rem = total_m % (24 * 60)
    h = rem // 60
    m = rem % 60
    return f"{d}d {h}h {m}m"


def _validation_status(can_calc, in_scope, delta_d, jira_nan):
    if not can_calc:
        return "Missing transition"
    if not in_scope:
        return "Out of scope"
    if jira_nan:
        return "Missing Jira value"
    if abs(delta_d) <= 2.0:
        return "Match"
    if abs(delta_d) <= 7.0:
        return "Minor difference"
    return "Significant difference"


# ── Per-epic calculation ──────────────────────────────────────────────────────

def _calc_one(key: str, grp: pd.DataFrame, metric: str) -> dict:
    grp = grp.sort_values("status_time").reset_index(drop=True)
    created       = grp["created"].iloc[0]
    tribe         = str(grp["tribe"].iloc[0]).strip() if "tribe" in grp.columns else ""
    squad         = str(grp["squad"].iloc[0]).strip() if "squad" in grp.columns else ""
    fix_versions  = str(grp["fix_versions"].iloc[0]).strip() if "fix_versions" in grp.columns else ""
    first_impl    = _first(grp, {IMPL})
    in_scope      = bool(pd.notna(first_impl) and first_impl >= SCOPE_DATE)
    quarter       = _assign_quarter(first_impl)
    impl_exit_ts  = _impl_exit(grp)

    # ── Key timestamps ────────────────────────────────────────────────────────
    first_disc      = _first(grp, {DISC})
    first_disc_comp = _first(grp, {DISC_COMP})
    first_del_com   = _first(grp, {DEL_COMMIT})
    del_start       = _delivery_start(grp)

    # ── Metric calculation ────────────────────────────────────────────────────
    can_calc = True
    note = ""
    active_h = 0.0
    oh_h = 0.0
    metric_start = pd.NaT

    if metric == "Discovery Cycle Time":
        active_h = _sum_h(grp, {DISC})
        oh_h = 0.0
        metric_start = first_disc
        can_calc = active_h > 0
        note = "no Discovery rows" if not can_calc else ""

    elif metric == "Discovery Lead Time":
        active_h = _sum_h(grp, {DISC})
        disc_end = _first(grp, {DISC_COMP, DEL_COMMIT, IMPL})
        oh_h = _oh_between(grp, first_disc, disc_end)
        metric_start = first_disc
        can_calc = active_h > 0
        note = "no Discovery rows" if not can_calc else ""

    elif metric == "Delivery Cycle Time":
        active_h = _sum_h(grp, DELIVERY_ACTIVE) if pd.notna(del_start) else 0.0
        oh_h = 0.0
        metric_start = del_start
        can_calc = pd.notna(del_start) and _sum_h(grp, {IMPL}) > 0
        if not can_calc:
            note = "no delivery start (Disc Completed / Del Committed)" if _sum_h(grp, {IMPL}) > 0 else "no Implementation"

    elif metric == "Delivery Lead Time":
        active_h = _sum_h(grp, DELIVERY_ACTIVE) if pd.notna(del_start) else 0.0
        oh_h = _oh_between(grp, del_start, impl_exit_ts)
        metric_start = del_start
        can_calc = pd.notna(del_start) and _sum_h(grp, {IMPL}) > 0
        if not can_calc:
            note = "no delivery start or no Implementation"

    elif metric == "Time to Market":
        active_h = _sum_h(grp, TTM_ACTIVE) if pd.notna(first_disc) else 0.0
        oh_h = _oh_between(grp, first_disc, impl_exit_ts)
        metric_start = first_disc
        can_calc = pd.notna(first_disc) and _sum_h(grp, {IMPL}) > 0
        if not can_calc:
            note = "no Discovery or no Implementation"

    elif metric == "ILT Proxy":
        # Old Implementation Lead Time: Implementation + all On Hold after first Impl entry
        active_h = _sum_h(grp, {IMPL})
        oh_h = _oh_after(grp, first_impl)
        metric_start = first_impl
        can_calc = active_h > 0
        note = "no Implementation" if not can_calc else ""

    total_h = (active_h + oh_h) if can_calc else np.nan
    total_d = total_h / 24 if not np.isnan(total_h) else np.nan

    # Jira reference = Implementation time_in_status
    impl_h_raw = _sum_h(grp, {IMPL})
    jira_h = impl_h_raw if impl_h_raw > 0 else np.nan
    jira_d = jira_h / 24 if not np.isnan(jira_h) else np.nan

    delta_d = (total_d - jira_d) if (not np.isnan(total_d) and not np.isnan(jira_d)) else np.nan
    v_status = _validation_status(can_calc, in_scope, delta_d, np.isnan(jira_h))

    return {
        "key":                              key,
        "selected_metric":                  metric,
        "created":                          created,
        "metric_start_timestamp":           metric_start,
        "first_discovery_timestamp":        first_disc,
        "first_discovery_completed_timestamp": first_disc_comp,
        "first_delivery_committed_timestamp":  first_del_com,
        "first_implementation_timestamp":   first_impl,
        "implementation_exit_timestamp":    impl_exit_ts,
        "in_scope_15_sep":                  in_scope,
        "quarter":                          quarter,
        "active_status_duration_hours":     round(active_h, 4) if can_calc else np.nan,
        "included_on_hold_duration_hours":  round(oh_h, 4),
        "calculated_metric_hours":          round(total_h, 4) if can_calc else np.nan,
        "calculated_metric_days":           round(total_d, 4) if can_calc else np.nan,
        "jira_comparison_hours":            round(jira_h, 4) if not np.isnan(jira_h) else np.nan,
        "jira_display_value":               format_jira(jira_h),
        "delta_days":                       round(delta_d, 2) if not np.isnan(delta_d) else np.nan,
        "validation_status":                v_status,
        "included_status_rows":             int(len(grp[grp["sn"].isin(TTM_ACTIVE)])),
        "excluded_status_rows":             int(len(grp[grp["sn"].isin({"canceled", "rejected"})])),
        "notes":                            note,
        "tribe":                            tribe,
        "squad":                            squad,
        "fix_versions":                     fix_versions,
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_all(path: str) -> dict[str, pd.DataFrame]:
    df = pd.read_excel(path)
    df = df.sort_values(["key", "status_time"]).reset_index(drop=True)
    df["sn"] = df["status"].str.strip().str.lower()

    all_metrics = [
        "Discovery Cycle Time",
        "Discovery Lead Time",
        "Delivery Cycle Time",
        "Delivery Lead Time",
        "Time to Market",
        "ILT Proxy",
    ]

    results: dict[str, pd.DataFrame] = {}
    for metric in all_metrics:
        records = [_calc_one(k, g, metric) for k, g in df.groupby("key")]
        results[metric] = pd.DataFrame(records)

    return results


def data_quality(df: pd.DataFrame, metric: str) -> dict:
    """Compute data quality summary for a metric dataframe."""
    inscope = df[df["in_scope_15_sep"]]
    can_calc = inscope[inscope["calculated_metric_days"].notna()]
    missing_jira = can_calc[can_calc["jira_comparison_hours"].isna()]
    excluded = inscope[inscope["calculated_metric_days"].isna()]

    n_scope   = len(can_calc)
    n_miss    = len(missing_jira)
    n_excl    = len(excluded)
    pct_excl  = n_excl / max(len(inscope), 1)

    if pct_excl < 0.1:
        quality = "Good"
    elif pct_excl < 0.3:
        quality = "Warning"
    else:
        quality = "Issue"

    return {
        "epics_in_scope": n_scope,
        "missing_jira":   n_miss,
        "excluded":       n_excl,
        "quality":        quality,
    }
