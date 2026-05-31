# Implementation Lead Time Dashboard

A local Streamlit dashboard that reproduces the Power BI **Implementation Lead Time** view from the QBR tracking system.

---

## How to Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the dashboard

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. Place `QBR time in status.xlsx` in the same folder as `app.py`.

---

## Input File

**`QBR time in status.xlsx`** — Sheet1 with columns:

| Column | Type | Description |
|--------|------|-------------|
| `key` | string | Epic identifier (e.g. QBR-1990) |
| `created` | datetime | Epic creation date |
| `status` | string | Jira status name |
| `time_in_status` | float | Hours spent in this status period |
| `status_time` | datetime | Timestamp when the epic entered this status |

Dates are already parsed as datetime by pandas (`datetime64[us]`). No serial-date conversion is needed.

---

## How Implementation Lead Time Is Calculated

**Formula:**

```
ILT = Σ time_in_status (where status = 'Implementation')
    + Σ time_in_status (where status = 'On Hold' AND On Hold entry ≥ first Implementation entry)
```

**Step-by-step:**

1. Group all rows by `key`.
2. Sort each group by `status_time` ascending.
3. Find the first row where `status = 'Implementation'` → this is `first_impl_entry`.
4. Sum `time_in_status` for all Implementation rows.
5. Sum `time_in_status` for all On Hold rows whose `status_time ≥ first_impl_entry`.
6. Add both sums. Divide by 24 to convert hours → days.
7. Round display to 2 decimal places.

---

## On Hold Handling

- **On Hold rows before the first Implementation entry are excluded.** These represent pre-implementation blockers unrelated to delivery.
- **On Hold rows on or after the first Implementation entry are included.** These represent pauses during the active implementation period.
- The `notes` column in `debug_output.csv` records how many On Hold rows were excluded for each Epic.

---

## In-Scope (15 Sep+) Filter

An Epic is **In Scope** if its **creation date ≥ 2025-09-15**, where "creation date" is defined as the first appearance of the Epic in **New** status — i.e., the `created` column in the Excel, which equals `status_time` of the first "New" row (verified: matches for 1421 of 1422 unique Epics; the one exception differs by only 10 minutes).

Filter behaviour:
- **All** (default): KPI cards, histogram, and table include **all** Epics in the selected Quarter, regardless of in-scope status. This is the setting shown in the Power BI screenshot, which includes Epics created as early as March 2025.
- **In Scope Only**: restricts KPI cards, histogram, and table to Epics with `created ≥ 2025-09-15`.

---

## Quarter Assignment

Per the dashboard definition, all Epics with `first_implementation_timestamp ≥ 2025-09-15` are assigned to **25Q4**. This matches the Power BI screenshot, which includes Epics with implementation start dates ranging from September 2025 through January 2026 — all labeled 25Q4.

Earlier Epics (before Sep 15, 2025) are assigned to calendar quarters (e.g., 25Q3, 25Q2) and are excluded from the default view.

---

## Canceled Epics

Canceled Epics **are included** if they have a valid Implementation status row. The `notes` column in `debug_output.csv` marks them with `"has Canceled rows"`. This matches the Power BI behavior, which does not exclude Epics solely because they were later Canceled — if implementation work occurred, it counts.

---

## KPI Comparison: Calculated vs Screenshot

KPIs depend on which filter is active:

| Filter setting | N | Mean | Median | P50 | P95 |
|---------------|---|------|--------|-----|-----|
| All + 25Q4 (current data) | 351 | 54.41 | 44.94 | 44.94 | 173.60 |
| In Scope Only + 25Q4 (current data) | 257 | 47.53 | 38.53 | 38.53 | 156.51 |
| **Screenshot target (All + 25Q4)** | — | **49.47** | **43.01** | **44.00** | **139.00** |

**Root cause of mismatch:** The Excel snapshot was extracted ≈ 2026-05-27; the Power BI screenshot was taken ≈ 2026-03-24 (back-calculated from QBR-1990 and QBR-2558 values). Since `time_in_status` is a running counter, Epics still in Implementation or On Hold have accumulated more hours in the more recent snapshot, inflating all aggregated KPIs.

---

## Individual Epic Regression Analysis

| Epic | Calculated | Screenshot | Jira (my) | Jira (screenshot) | Status |
|------|-----------|------------|-----------|-------------------|--------|
| QBR-1990 | 216.11 | 159.80 | 85d 19h 33m | 85d 19h 32m | **created=2025-03-31 → not in scope**. Calculated higher: On Hold period ongoing at screenshot time was ~74d; grew to 130d in current data. Jira ±1m: Excel stores 2059.5500h, actual ~2059.5333h. |
| QBR-2555 | 19.12 | 19.12 | 19d 2h 51m | 19d 2h 51m | **created=2025-09-01 → not in scope.** Calculated value matches. |
| QBR-2558 | 88.29 | 70.92 | 88d 7h 1m | (blank) | **created=2025-09-01 → not in scope.** Still in Implementation at screenshot time (70.92d); moved to Closed 2026-04-10. Jira blank = implementation not yet closed. |
| QBR-2008 | 98.00 | 98.00 | 98d 0h 0m | (blank) | **created=2025-03-31 → not in scope.** Calculated matches; Jira blank in screenshot. |
| QBR-2850 | 21.38 | 21.38 | 21d 9h 6m | 21d 9h 6m | **created=2025-09-17 → IN SCOPE ✓. Matches.** |
| QBR-2874 | 1.01 | 1.01 | 1d 0h 12m | 1d 0h 12m | **created=2025-09-17 → IN SCOPE ✓. Matches.** |
| QBR-2875 | 1.04 | 1.04 | 1d 0h 57m | 1d 0h 57m | **created=2025-09-17 → IN SCOPE ✓. Matches.** |
| QBR-2107 | 110.11 | 110.11 | 110d 2h 35m | 110d 2h 35m | **created=2025-04-03 → not in scope.** Calculated matches. |
| QBR-2675 | 66.83 | 66.83 | 66d 20h 0m | 66d 20h 0m | **created=2025-09-11 → not in scope.** Calculated matches. |

**7 of 9 calculated values match exactly.** The 2 mismatches (QBR-1990 and QBR-2558) are caused by the Excel snapshot being more recent than the screenshot (~May 2026 vs ~March 2026).

Of the 9 visible Epics, only 3 are **in scope** by creation date (QBR-2850, QBR-2874, QBR-2875). The other 6 appear in the screenshot because the "In Scope (15 Sep+)" filter was set to **All**, which includes all Epics regardless of creation date.

---

## debug_output.csv

Generated automatically when the app starts (or when the Python script is run directly). Contains one row per Epic that has at least one Implementation status row.

| Column | Description |
|--------|-------------|
| `key` | Epic identifier |
| `first_implementation_timestamp` | Datetime of first Implementation entry |
| `in_scope_15_sep` | True if first_impl ≥ 2025-09-15 |
| `quarter` | Assigned quarter (25Q4 for all in-scope) |
| `implementation_duration_hours` | Sum of Implementation time_in_status (hours) |
| `implementation_duration_days` | Implementation hours ÷ 24 |
| `included_on_hold_duration_hours` | Sum of On Hold time_in_status after first impl (hours) |
| `included_on_hold_duration_days` | On Hold hours ÷ 24 |
| `calculated_implementation_lead_time_hours` | Total ILT in hours |
| `calculated_implementation_lead_time_days` | Total ILT in days |
| `jira_display_value` | Implementation hours formatted as Xd Yh Zm |
| `included_status_rows` | Count of status rows used in calculation |
| `notes` | Flags: Canceled rows, excluded On Hold, multiple Implementation stints |
#commit test