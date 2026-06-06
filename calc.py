"""Agile CoE Time Metrics — calculation engine"""
import re
import numpy as np
import pandas as pd

DISC       = "discovery"
DISC_COMP  = "discovery completed"
DEL_COMMIT = "delivery committed"
IMPL       = "implementation"
ON_HOLD    = "on hold"

DELIVERY_ACTIVE = {DISC_COMP, DEL_COMMIT, IMPL}
TTM_ACTIVE      = {DISC, DISC_COMP, DEL_COMMIT, IMPL}
COMPLETED_STATUSES = {"released/completed", "completed", "released / measurement", "done"}


def _oh_between(oh_rows: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    if pd.isna(start) or oh_rows.empty:
        return 0.0
    mask = oh_rows["status_time"] >= start
    if pd.notna(end):
        mask = mask & (oh_rows["status_time"] < end)
    return float(oh_rows.loc[mask, "time_in_status"].sum())


def _impl_exit(grp: pd.DataFrame) -> pd.Timestamp:
    impl = grp[grp["sn"] == IMPL].sort_values("status_time")
    if impl.empty:
        return pd.NaT
    last = impl.iloc[-1]
    after = grp[grp["status_time"] > last["status_time"]]
    if not after.empty:
        return after["status_time"].iloc[0]
    return last["status_time"] + pd.Timedelta(hours=float(last["time_in_status"]))


def _delivery_start(grp: pd.DataFrame) -> pd.Timestamp:
    candidates = []
    for sn in (DISC_COMP, DEL_COMMIT):
        rows = grp[grp["sn"] == sn]["status_time"]
        if not rows.empty:
            candidates.append(rows.min())
    return min(candidates) if candidates else pd.NaT


def _parse_quarters(fv) -> list:
    if pd.isna(fv):
        return []
    return re.findall(r"\d{2}Q\d", str(fv))


def _calc_epic(key: str, grp: pd.DataFrame) -> dict:
    grp = grp.sort_values("status_time").reset_index(drop=True)

    created  = grp["created"].iloc[0]
    tribe_raw = grp["tribe"].iloc[0] if "tribe" in grp.columns else None
    tribe    = str(tribe_raw).strip() if pd.notna(tribe_raw) else ""
    fix_raw  = grp["fix_versions"].iloc[0] if "fix_versions" in grp.columns else None
    quarters = _parse_quarters(fix_raw)

    disc_rows  = grp[grp["sn"] == DISC]
    impl_rows  = grp[grp["sn"] == IMPL]
    oh_rows    = grp[grp["sn"] == ON_HOLD]
    comp_rows  = grp[grp["sn"].isin(COMPLETED_STATUSES)]
    rel_rows   = grp[grp["sn"] == "released/completed"]

    first_disc    = disc_rows["status_time"].min() if not disc_rows.empty else pd.NaT
    del_start     = _delivery_start(grp)
    impl_exit_ts  = _impl_exit(grp)
    completed_date = comp_rows["status_time"].min() if not comp_rows.empty else pd.NaT

    # TTM: from first exit out of New → last entry into Released/Completed
    non_new       = grp[(grp["sn"] != "new") & (grp["sn"] != "canceled")]
    ttm_start_ts  = non_new["status_time"].min() if not non_new.empty else pd.NaT
    ttm_end_ts    = rel_rows["status_time"].max() if not rel_rows.empty else pd.NaT

    # Started: first exit from New into any status except Canceled
    started_ts    = non_new["status_time"].min() if not non_new.empty else pd.NaT

    # Discovery Cycle Time — sum of time in Discovery
    disc_ct_d = float(disc_rows["time_in_status"].sum()) / 24 if not disc_rows.empty else np.nan

    # Discovery Lead Time — Discovery CT + On Hold within Discovery window
    if not disc_rows.empty:
        disc_lt_d = (
            float(disc_rows["time_in_status"].sum())
            + _oh_between(oh_rows, first_disc, del_start)
        ) / 24
    else:
        disc_lt_d = np.nan

    # Delivery Cycle Time — Implementation time only (active work in Implementation status)
    if not impl_rows.empty:
        del_ct_d = float(impl_rows["time_in_status"].sum()) / 24
    else:
        del_ct_d = np.nan

    # Delivery Lead Time — Implementation CT + On Hold from delivery start to impl exit
    if not impl_rows.empty:
        oh_anchor = del_start if pd.notna(del_start) else impl_rows["status_time"].min()
        del_lt_d = (
            float(impl_rows["time_in_status"].sum())
            + _oh_between(oh_rows, oh_anchor, impl_exit_ts)
        ) / 24
    else:
        del_lt_d = np.nan

    # Time to Market — calendar days from first exit of New to last Released/Completed entry
    if pd.notna(ttm_start_ts) and pd.notna(ttm_end_ts):
        ttm_d = (ttm_end_ts - ttm_start_ts).total_seconds() / 86400
    else:
        ttm_d = np.nan

    def r(v):
        return round(float(v), 2) if pd.notna(v) and not np.isnan(float(v)) else np.nan

    return {
        "key":            key,
        "created":        pd.Timestamp(created).normalize() if pd.notna(created) else pd.NaT,
        "completed_date": pd.Timestamp(completed_date).normalize() if pd.notna(completed_date) else pd.NaT,
        "started_date":   pd.Timestamp(started_ts).normalize() if pd.notna(started_ts) else pd.NaT,
        "tribe":          tribe,
        "quarters":       quarters,
        "quarters_str":   ", ".join(quarters),
        "disc_ct_d":      r(disc_ct_d),
        "disc_lt_d":      r(disc_lt_d),
        "del_ct_d":       r(del_ct_d),
        "del_lt_d":       r(del_lt_d),
        "ttm_d":          r(ttm_d),
    }


def compute_metrics(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df = df.sort_values(["key", "status_time"]).reset_index(drop=True)
    df["sn"] = df["status"].str.strip().str.lower()
    records = [_calc_epic(k, g) for k, g in df.groupby("key")]
    return pd.DataFrame(records)
