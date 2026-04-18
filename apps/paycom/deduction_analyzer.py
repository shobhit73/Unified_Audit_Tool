import io
import re
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st


# st.set_page_config(page_title="Deduction Analyzer", layout="wide")


# -----------------------------
# Helpers
# -----------------------------

def norm_text(val) -> str:
    if pd.isna(val):
        return ""
    s = str(val).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def upper_clean(val) -> str:
    return norm_text(val).upper()


def yes_no(val) -> str:
    s = upper_clean(val)
    if s in {"Y", "YES", "TRUE", "1"}:
        return "Yes"
    if s in {"N", "NO", "FALSE", "0"}:
        return "No"
    return s.title() if s else ""


def is_open_ended_date(val) -> bool:
    """Treat dates like 00/00/0000, 0/0/0000, 0000, blank-zero hybrids as open-ended.
    If any zero-date pattern is present, we treat the deduction as running/open.
    """
    if pd.isna(val):
        return False
    s = str(val).strip()
    if not s:
        return False
    s_nospace = s.replace(" ", "")
    zero_patterns = {
        "0000", "00/00/0000", "0/0/0000", "00-00-0000", "0-0-0000",
        "00/00/00", "0/0/00"
    }
    if s_nospace in zero_patterns:
        return True
    if re.search(r"(^|\D)0{4}(\D|$)", s_nospace):
        return True
    if s_nospace.startswith("00/") or s_nospace.endswith("/0000"):
        return True
    return False


def parse_date_safe(val) -> pd.Timestamp:
    if pd.isna(val):
        return pd.NaT
    if is_open_ended_date(val):
        return pd.NaT
    s = str(val).strip()
    if not s:
        return pd.NaT
    return pd.to_datetime(s, errors="coerce")


def classify_item(type_code: str, description: str) -> str:
    """Operational classification for UZIO setup.
    You can tweak this later to match your business rules.
    """
    code = upper_clean(type_code)
    desc = upper_clean(description)

    tax_keywords = [
        "WITHHOLDING TAX", "SOCIAL SECURITY", "MEDICARE", "FUTA", "SUTA",
        "WORKERS COMPENSATION", "STATE W/H", "LOCAL", "SIT", "FWT",
    ]
    contribution_keywords = [" MATCH", "MEMO", "EMPLOYER MEMO", "ER MEMO"]
    deduction_keywords = [
        "MEDICAL", "DENTAL", "VISION", "401K", "ROTH", "LOAN", "AD&D",
        "STD", "VOL EE LIFE", "SUPPORT ORDER", "GARNISH", "EARNED WAGE ACCESS",
        "HEALTHCUES", "REIMBURSE", "OVERPAYMENT",
    ]

    # Special handling for NY items based on your setup context.
    if code in {"NSD", "PFL"} or desc in {"NEW YORK SDI", "NY PAID FAMILY LEAVE"}:
        return "Tax / Statutory Payroll Item"

    if any(k in desc for k in contribution_keywords):
        return "Contribution"

    if any(k in desc for k in tax_keywords):
        return "Tax / Statutory Payroll Item"

    if any(k in desc for k in deduction_keywords):
        return "Deduction"

    return "Review"


def classify_value_basis(group: pd.DataFrame) -> str:
    amt_non_zero = pd.to_numeric(group["Amount_num"], errors="coerce").fillna(0).ne(0).any() if "Amount_num" in group else False
    pct_non_zero = pd.to_numeric(group["Percent_num"], errors="coerce").fillna(0).ne(0).any() if "Percent_num" in group else False

    if amt_non_zero and pct_non_zero:
        return "Amount and Percent"
    if amt_non_zero:
        return "Amount"
    if pct_non_zero:
        return "Percent"
    return "No Non-Zero Amount/Percent Found"


def all_rows_zero_flag(group: pd.DataFrame) -> tuple[str, str]:
    amt_series = pd.to_numeric(group.get("Amount_num", pd.Series(dtype=float)), errors="coerce").fillna(0)
    pct_series = pd.to_numeric(group.get("Percent_num", pd.Series(dtype=float)), errors="coerce").fillna(0)
    all_zero = amt_series.eq(0).all() and pct_series.eq(0).all()
    if all_zero:
        return "Yes", f"For all {len(group)} row(s), Amount and Percent are 0.00 or blank/zero after normalization."
    return "No", "At least one row has a non-zero Amount or Percent."


def map_presence(in_sched: bool, in_prior: bool) -> str:
    if in_sched and in_prior:
        return "Present in Both"
    if in_sched:
        return "Scheduled Report Only"
    if in_prior:
        return "Prior Payroll Only"
    return "Not Found"


def recommend_action(row, analysis_year: int) -> str:
    active = row.get("Active Employee Count", 0) or 0
    terminated = row.get("Terminated Employee Count", 0) or 0
    classification = row.get("Classification", "")
    running = row.get("Running Flag", "No") == "Yes"
    payroll_presence = row.get("Found in Prior Payroll", "No") == "Yes"
    zero_flag = row.get("All Rows Zero Amount/Percent?", "No") == "Yes"
    latest_stop = row.get("Latest Actual Stop Date Parsed")
    setup_relevance = row.get("Setup Relevance", "")

    if classification == "Contribution":
        return "Review - Contribution"
    if classification == "Tax / Statutory Payroll Item":
        return "Review - Tax/Statutory"
    if active > 0:
        return "Keep"
    if running and active == 0 and terminated > 0:
        return "Remove Candidate"
    if pd.notna(latest_stop) and latest_stop < pd.Timestamp(f"{analysis_year}-01-01") and active == 0:
        return "Remove Candidate"
    if payroll_presence and setup_relevance == "Deduction Setup Needed":
        return "Keep"
    if zero_flag and active == 0 and terminated == 0:
        return "Review"
    return "Review"


def setup_relevance(classification: str) -> str:
    if classification == "Deduction":
        return "Deduction Setup Needed"
    if classification == "Contribution":
        return "Contribution Setup Needed"
    if classification == "Tax / Statutory Payroll Item":
        return "Tax Handling Needed"
    return "Review"


# -----------------------------
# Scheduled deduction processing
# -----------------------------

def build_scheduled_summary(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_cols = [
        "EE Code", "EE Status", "Deduction Code", "Deduction Desc", "Memo Only",
        "Amount", "Percent", "Start Date", "Stop Date"
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Scheduled deduction file is missing columns: {missing}")

    work = df.copy()
    work["EE Code"] = work["EE Code"].astype(str).str.strip()
    work["EE Status"] = work["EE Status"].astype(str).str.strip().str.upper()
    work["Deduction Code"] = work["Deduction Code"].map(norm_text)
    work["Deduction Desc"] = work["Deduction Desc"].map(norm_text)
    work["Memo Only Clean"] = work["Memo Only"].map(yes_no)
    work["Amount_num"] = pd.to_numeric(work["Amount"], errors="coerce").fillna(0)
    work["Percent_num"] = pd.to_numeric(work["Percent"], errors="coerce").fillna(0)
    work["Start Date Text"] = work["Start Date"].astype(str).str.strip()
    work["Stop Date Text"] = work["Stop Date"].astype(str).str.strip()
    work["Start Open"] = work["Start Date"].apply(is_open_ended_date)
    work["Stop Open"] = work["Stop Date"].apply(is_open_ended_date)
    work["Open Date Flag"] = work["Start Open"] | work["Stop Open"]
    work["Start Date Parsed"] = work["Start Date"].apply(parse_date_safe)
    work["Stop Date Parsed"] = work["Stop Date"].apply(parse_date_safe)

    group_cols = ["Deduction Code", "Deduction Desc"]

    def summarize_group(g: pd.DataFrame) -> pd.Series:
        running = g["Open Date Flag"].any()
        actual_rows = g.loc[~g["Open Date Flag"]].copy()
        active_ee = g.loc[g["EE Status"] == "A", "EE Code"].nunique()
        term_ee = g.loc[g["EE Status"] == "T", "EE Code"].nunique()
        v_ee = g.loc[g["EE Status"] == "V", "EE Code"].nunique()
        value_basis = classify_value_basis(g)
        zero_flag, zero_note = all_rows_zero_flag(g)

        if running:
            start_display = "00/00/0000"
            stop_display = "00/00/0000"
        else:
            start_candidates = actual_rows["Start Date Parsed"].dropna()
            stop_candidates = actual_rows["Stop Date Parsed"].dropna()
            start_display = start_candidates.min().strftime("%m/%d/%Y") if not start_candidates.empty else ""
            stop_display = stop_candidates.max().strftime("%m/%d/%Y") if not stop_candidates.empty else ""

        memo_vals = [x for x in g["Memo Only Clean"].dropna().unique().tolist() if x != ""]
        memo_out = ", ".join(sorted(memo_vals)) if memo_vals else ""

        latest_stop_parsed = actual_rows["Stop Date Parsed"].dropna().max() if not actual_rows.empty else pd.NaT
        earliest_start_parsed = actual_rows["Start Date Parsed"].dropna().min() if not actual_rows.empty else pd.NaT

        return pd.Series({
            "Memo Only": memo_out,
            "Running Flag": "Yes" if running else "No",
            "Date Classification": "Running Deduction" if running else "Actual Dated Deduction",
            "Start Date": start_display,
            "Stop Date": stop_display,
            "Earliest Actual Start Date Parsed": earliest_start_parsed,
            "Latest Actual Stop Date Parsed": latest_stop_parsed,
            "Scheduled Row Count": len(g),
            "Scheduled Distinct Employees": g["EE Code"].nunique(),
            "Active Employee Count": active_ee,
            "Terminated Employee Count": term_ee,
            "V Status Employee Count": v_ee,
            "Amount or Percent": value_basis,
            "All Rows Zero Amount/Percent?": zero_flag,
            "Zero Value Note": zero_note,
        })

    summary = work.groupby(group_cols, dropna=False).apply(summarize_group).reset_index()
    return summary, work


# -----------------------------
# Prior payroll processing
# -----------------------------

def build_prior_summary(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_cols = ["EE Code", "Type Code", "Type Description", "Amount"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Prior payroll file is missing columns: {missing}")

    work = df.copy()
    work["EE Code"] = work["EE Code"].astype(str).str.strip()
    work["Type Code"] = work["Type Code"].map(norm_text)
    work["Type Description"] = work["Type Description"].map(norm_text)
    work["Amount_num"] = pd.to_numeric(work["Amount"], errors="coerce").fillna(0)

    # Filter out obvious non-deduction lines. Keep taxes/contributions because they help the analysis.
    excluded_desc = {
        "REGULAR", "BONUS (HOURS)", "PTO", "PAID TIME OFF", "NET CHECK",
        "NET DISTRIBUTION 1", "NET DISTRIBUTION 2", "RETRO REGULAR PAY"
    }
    filtered = work.loc[~work["Type Description"].str.upper().isin(excluded_desc)].copy()

    summary = (
        filtered.groupby(["Type Code", "Type Description"], dropna=False)
        .agg(
            Prior_Payroll_Row_Count=("EE Code", "size"),
            Prior_Payroll_Distinct_Employees=("EE Code", "nunique"),
            Prior_Payroll_Total_Amount=("Amount_num", "sum"),
            Prior_Payroll_NonZero_Row_Count=("Amount_num", lambda s: int(s.ne(0).sum())),
        )
        .reset_index()
        .rename(columns={"Type Code": "Deduction Code", "Type Description": "Deduction Desc"})
    )
    return summary, filtered


# -----------------------------
# Merge / final workbook
# -----------------------------

def build_master_sheet(scheduled_summary: pd.DataFrame, prior_summary: pd.DataFrame, analysis_year: int) -> pd.DataFrame:
    master = pd.merge(
        scheduled_summary,
        prior_summary,
        on=["Deduction Code", "Deduction Desc"],
        how="outer",
    )

    for col in [
        "Scheduled Row Count", "Scheduled Distinct Employees", "Active Employee Count",
        "Terminated Employee Count", "V Status Employee Count", "Prior_Payroll_Row_Count",
        "Prior_Payroll_Distinct_Employees", "Prior_Payroll_Total_Amount", "Prior_Payroll_NonZero_Row_Count",
    ]:
        if col in master.columns:
            master[col] = master[col].fillna(0)

    master["Found in Scheduled Report"] = np.where(master["Scheduled Row Count"].fillna(0).gt(0), "Yes", "No")
    master["Found in Prior Payroll"] = np.where(master["Prior_Payroll_Row_Count"].fillna(0).gt(0), "Yes", "No")
    master["Source Presence"] = master.apply(
        lambda r: map_presence(r["Found in Scheduled Report"] == "Yes", r["Found in Prior Payroll"] == "Yes"),
        axis=1,
    )

    # Fill scheduled-only columns for prior-only rows.
    for col in [
        "Memo Only", "Running Flag", "Date Classification", "Start Date", "Stop Date",
        "Amount or Percent", "All Rows Zero Amount/Percent?", "Zero Value Note"
    ]:
        if col not in master.columns:
            master[col] = ""
        master[col] = master[col].fillna("")

    # Classification can come from either source.
    master["Classification"] = master.apply(
        lambda r: classify_item(r.get("Deduction Code", ""), r.get("Deduction Desc", "")),
        axis=1,
    )
    master["Setup Relevance"] = master["Classification"].map(setup_relevance)
    master["Recommendation"] = master.apply(lambda r: recommend_action(r, analysis_year), axis=1)

    master["Review Note"] = ""
    master.loc[
        (master["Found in Scheduled Report"] == "No") & (master["Found in Prior Payroll"] == "Yes"),
        "Review Note",
    ] = "Present in prior payroll but not found in scheduled deduction report."
    master.loc[
        (master["Found in Scheduled Report"] == "Yes") & (master["Found in Prior Payroll"] == "No"),
        "Review Note",
    ] = "Present in scheduled deduction report but not used in this prior payroll file/pay period."
    master.loc[
        master["All Rows Zero Amount/Percent?"] == "Yes",
        "Review Note",
    ] = master["Review Note"].astype(str).str.strip() + " All scheduled rows have zero Amount/Percent."

    ordered_cols = [
        "Deduction Code", "Deduction Desc", "Classification", "Setup Relevance", "Recommendation",
        "Source Presence", "Found in Scheduled Report", "Found in Prior Payroll",
        "Running Flag", "Date Classification", "Start Date", "Stop Date", "Memo Only",
        "Scheduled Row Count", "Scheduled Distinct Employees", "Active Employee Count",
        "Terminated Employee Count", "V Status Employee Count",
        "Amount or Percent", "All Rows Zero Amount/Percent?", "Zero Value Note",
        "Prior_Payroll_Row_Count", "Prior_Payroll_Distinct_Employees",
        "Prior_Payroll_Total_Amount", "Prior_Payroll_NonZero_Row_Count",
        "Review Note", "Earliest Actual Start Date Parsed", "Latest Actual Stop Date Parsed",
    ]
    existing = [c for c in ordered_cols if c in master.columns]
    remaining = [c for c in master.columns if c not in existing]
    master = master[existing + remaining].sort_values(["Recommendation", "Deduction Code", "Deduction Desc"]).reset_index(drop=True)
    return master


def to_excel_bytes(master: pd.DataFrame, scheduled_detail: pd.DataFrame, prior_detail: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        master.to_excel(writer, index=False, sheet_name="Master_Summary")
        scheduled_detail.to_excel(writer, index=False, sheet_name="Scheduled_Detail")
        prior_detail.to_excel(writer, index=False, sheet_name="Prior_Payroll_Detail")

        wb = writer.book
        ws = writer.sheets["Master_Summary"]

        # Freeze header
        ws.freeze_panes = "A2"

        # Light formatting / widths
        for col_cells in ws.columns:
            max_len = 0
            col_letter = col_cells[0].column_letter
            for cell in col_cells[:2000]:
                try:
                    max_len = max(max_len, len(str(cell.value)) if cell.value is not None else 0)
                except Exception:
                    pass
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 35)

        from openpyxl.styles import PatternFill, Font
        green_fill = PatternFill("solid", fgColor="E2F0D9")
        yellow_fill = PatternFill("solid", fgColor="FFF2CC")
        red_fill = PatternFill("solid", fgColor="F4CCCC")
        blue_fill = PatternFill("solid", fgColor="D9EAF7")
        bold = Font(bold=True)

        for cell in ws[1]:
            cell.font = bold
            cell.fill = blue_fill

        headers = [c.value for c in ws[1]]
        idx = {name: i + 1 for i, name in enumerate(headers)}

        for row in range(2, ws.max_row + 1):
            running = ws.cell(row, idx.get("Running Flag", 1)).value == "Yes" if idx.get("Running Flag") else False
            zero_flag = ws.cell(row, idx.get("All Rows Zero Amount/Percent?", 1)).value == "Yes" if idx.get("All Rows Zero Amount/Percent?") else False
            active = ws.cell(row, idx.get("Active Employee Count", 1)).value or 0 if idx.get("Active Employee Count") else 0
            term = ws.cell(row, idx.get("Terminated Employee Count", 1)).value or 0 if idx.get("Terminated Employee Count") else 0
            rec = ws.cell(row, idx.get("Recommendation", 1)).value if idx.get("Recommendation") else ""

            fill = None
            if rec == "Remove Candidate":
                fill = red_fill
            elif zero_flag:
                fill = yellow_fill
            elif running:
                fill = green_fill

            if fill:
                for col in range(1, ws.max_column + 1):
                    ws.cell(row, col).fill = fill

    output.seek(0)
    return output.getvalue()


# -----------------------------
# UI
# -----------------------------

def render_ui():
    st.title    ("Scheduled Deduction + Prior Payroll Analyzer")
    st.write(
        "Upload a Paycom **Scheduled Deduction Report** and a **Prior Payroll** file. "
        "The app will create one smart summary sheet to help decide what should be set up as company-level deductions in UZIO."
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        scheduled_file = st.file_uploader("Scheduled Deduction Report (.xlsx)", type=["xlsx"], key="scheduled")
    with col2:
        prior_file = st.file_uploader("Prior Payroll File (.xlsx)", type=["xlsx"], key="prior")
    with col3:
        analysis_year = st.number_input("Analysis year for end-date checks", min_value=2020, max_value=2035, value=2026, step=1)

    run = st.button("Analyze Files", type="primary", use_container_width=True)

    if run:
        if not scheduled_file or not prior_file:
            st.error("Please upload both files first.")
            st.stop()

        try:
            sched_df = pd.read_excel(scheduled_file, sheet_name=0)
            prior_df = pd.read_excel(prior_file, sheet_name=0)

            scheduled_summary, scheduled_detail = build_scheduled_summary(sched_df)
            prior_summary, prior_detail = build_prior_summary(prior_df)
            master = build_master_sheet(scheduled_summary, prior_summary, analysis_year=int(analysis_year))
            excel_bytes = to_excel_bytes(master, scheduled_detail, prior_detail)

            st.success("Analysis completed.")

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total items in master", len(master))
            k2.metric("Keep", int((master["Recommendation"] == "Keep").sum()))
            k3.metric("Remove candidate", int((master["Recommendation"] == "Remove Candidate").sum()))
            k4.metric("Review buckets", int(master["Recommendation"].astype(str).str.startswith("Review").sum()))

            st.subheader("Master Summary Preview")
            st.dataframe(master, use_container_width=True, height=500)

            st.download_button(
                "Download Smart Analysis Workbook",
                data=excel_bytes,
                file_name=f"deduction_smart_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            with st.expander("Business rules used"):
                st.markdown(
                    """
    - If **any row** of a scheduled deduction has `0000` in Start Date or Stop Date, it is treated as a **Running Deduction**.
    - If a scheduled deduction is running, the tool keeps that running classification and does not rely on actual dates for decisioning.
    - `A`, `T`, and `V` employee statuses are counted separately from the scheduled deduction report.
    - A deduction is flagged **All Rows Zero Amount/Percent = Yes** only if **every scheduled row** for that deduction has zero/blank normalized Amount and zero/blank normalized Percent.
    - Prior payroll lines ending with **Match** or **Memo** are classified as **Contribution**.
    - **NSD** and **PFL** are classified as **Tax / Statutory Payroll Item** in this version, based on your current working assumption.
    - Recommendation logic is a starting point and can be adjusted to match your final UZIO setup policy.
                    """
                )

        except Exception as e:
            st.exception(e)
