"""ADP - Prior Payroll Sanity Check Tool.

Cleans an ADP Prior Payroll file by fixing the two specific issues that
break downstream API ingestion:

  1. Duplicate rows for the same employee + pay period are folded into a
     single row using a non-destructive smart merge (no double-counting).
  2. The grand-total row at the very bottom of the file -- where the
     last employee's ID got bled into the totals row -- is removed.

Output is always CSV with the input's exact column headers preserved.
Input accepts .xlsx / .xls / .csv.
"""

import streamlit as st
import pandas as pd
import io
from utils.audit_utils import clean_money_val


def _find_col(df, candidates):
    """Case-insensitive exact-then-substring lookup of a column."""
    for cand in candidates:
        for c in df.columns:
            if str(c).strip().lower() == cand.lower():
                return c
    for cand in candidates:
        for c in df.columns:
            if cand.lower() in str(c).strip().lower():
                return c
    return None


def read_input_file(file):
    """Read the ADP file (xlsx/xls/csv), find the header row, and return the dataframe.

    Preserves original column names and order exactly. Does NOT strip the grand-total
    row -- the sanity-check pipeline does that explicitly so it can be reported.
    """
    file.seek(0)
    name = (file.name or "").lower()

    if name.endswith(".csv"):
        file.seek(0)
        df_peek = pd.read_csv(file, header=None, nrows=50, dtype=str)
        header_idx = 0
        for i, row in df_peek.iterrows():
            row_str = " ".join(str(x).lower() for x in row if pd.notna(x))
            if any(k in row_str for k in ["associate id", "employee id", "file #"]):
                header_idx = i
                break
        file.seek(0)
        df = pd.read_csv(file, header=header_idx, dtype=str)
        return df, header_idx, "Sheet1"

    xls = pd.ExcelFile(file)
    target_sheet = xls.sheet_names[0]
    if len(xls.sheet_names) > 1 and "criteria" in xls.sheet_names[0].lower():
        target_sheet = xls.sheet_names[1]
    df_peek = pd.read_excel(xls, sheet_name=target_sheet, header=None, nrows=50)
    header_idx = 0
    for i, row in df_peek.iterrows():
        row_str = " ".join(str(x).lower() for x in row if pd.notna(x))
        if any(k in row_str for k in ["associate id", "employee id", "file #"]):
            header_idx = i
            break
    df = pd.read_excel(xls, sheet_name=target_sheet, header=header_idx, dtype=str)
    return df, header_idx, target_sheet


def detect_grand_total_row(df):
    """Detect the bottom-of-file grand total where the last employee's ID leaked.

    Pattern (carried over from the audit tool):
      - last row's first few columns share values with the previous row
        (the leak), AND
      - some money column on the last row equals the sum of all preceding
        rows for that column (within 5%).

    Returns (cleaned_df, info_dict_or_None).
    """
    if len(df) < 2:
        return df, None

    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    shared = 0
    for c in df.columns[:5]:
        v_l = str(last_row[c]).strip()
        v_p = str(prev_row[c]).strip()
        if v_l and v_l == v_p and v_l.lower() != "nan":
            shared += 1
    if shared < 1:
        return df, None

    for c in df.columns:
        try:
            val_last = clean_money_val(last_row[c])
            if val_last <= 100:
                continue
            sum_rest = sum(clean_money_val(x) for x in df[c].iloc[:-1])
            if sum_rest > 0 and abs(val_last - sum_rest) < sum_rest * 0.05:
                eid_col = _find_col(df, ["Associate ID", "Employee ID", "File #"])
                first_col = _find_col(df, ["First Name"])
                last_col = _find_col(df, ["Last Name"])
                preview_eid = str(last_row[eid_col]) if eid_col else ""
                fn = str(last_row[first_col]).strip() if first_col and pd.notna(last_row[first_col]) else ""
                ln = str(last_row[last_col]).strip() if last_col and pd.notna(last_row[last_col]) else ""
                return df.iloc[:-1].copy(), {
                    "removed_employee_id": preview_eid,
                    "removed_employee_name": (fn + " " + ln).strip(),
                    "matched_on_column": str(c),
                    "matched_value": round(val_last, 2),
                    "expected_sum": round(sum_rest, 2),
                }
        except Exception:
            continue

    return df, None


def _smart_merge_value(values):
    """Pick the best value across duplicate rows for a single column.

    Rules:
      - Drop NaN / empty / dash placeholders
      - Among numeric candidates, take the one with the largest absolute value
        (avoids double-counting when one row is the skeleton 0 / dash row)
      - For non-numeric, take the first non-empty value
      - Fall back to the first raw value if everything is empty
    """
    cleaned = []
    for v in values:
        if pd.isna(v):
            continue
        sv = str(v).strip()
        if sv in ("", "-", "nan", "NaT"):
            continue
        cleaned.append(v)
    if not cleaned:
        return values[0] if len(values) > 0 else None

    best_num = None
    best_num_val = None
    for v in cleaned:
        try:
            num = clean_money_val(v)
            if best_num is None or abs(num) > abs(best_num_val):
                best_num = v
                best_num_val = num
        except Exception:
            continue
    if best_num is not None and best_num_val is not None and best_num_val != 0:
        return best_num
    return cleaned[0]


def merge_duplicate_pay_periods(df):
    """Fold duplicate (Employee ID, Pay Date [, Period Start, Period End]) rows
    into one row using smart merge.

    Returns (cleaned_df, list_of_merge_events).
    """
    eid_col = _find_col(df, ["Associate ID", "Employee ID", "File #"])
    pay_col = _find_col(df, ["Pay Date", "Check Date", "Pay Period End Date"])
    start_col = _find_col(df, ["Period Start", "Pay Period Start", "Start Date"])
    end_col = _find_col(df, ["Period End", "Pay Period End", "End Date"])

    if not eid_col or not pay_col:
        return df, []

    keys = [eid_col, pay_col]
    if start_col and start_col not in keys:
        keys.append(start_col)
    if end_col and end_col not in keys:
        keys.append(end_col)

    work = df.copy()
    work["_orig_idx"] = range(len(work))

    grouped = work.groupby(keys, dropna=False, sort=False)
    counts = grouped.size().reset_index(name="_n")
    dup_keys = counts[counts["_n"] > 1]
    if dup_keys.empty:
        return df.reset_index(drop=True), []

    keep_indices = []
    drop_indices = set()
    merge_events = []
    merged_records = []

    for key_vals, group in grouped:
        if len(group) == 1:
            keep_indices.append(group["_orig_idx"].iloc[0])
            continue

        first_idx = int(group["_orig_idx"].iloc[0])
        merged = {}
        for col in df.columns:
            merged[col] = _smart_merge_value(group[col].tolist())

        merged_records.append((first_idx, merged))
        drop_indices.update(int(i) for i in group["_orig_idx"].tolist())

        merge_events.append({
            "Employee ID": str(key_vals[0]),
            "Pay Date": str(key_vals[1]),
            "Rows merged": int(len(group)),
            "Kept canonical row at original index": first_idx,
        })

    cleaned_rows = []
    for i in range(len(df)):
        if i in drop_indices:
            continue
        cleaned_rows.append(df.iloc[i].to_dict())
    for first_idx, merged in merged_records:
        merged["_insert_at"] = first_idx
        cleaned_rows.append(merged)

    cleaned_rows.sort(key=lambda r: r.get("_insert_at", -1) if "_insert_at" in r else -1)
    for r in cleaned_rows:
        r.pop("_insert_at", None)

    cleaned = pd.DataFrame(cleaned_rows, columns=df.columns)
    return cleaned.reset_index(drop=True), merge_events


def render_ui():
    st.title("ADP - Prior Payroll Sanity Check")
    st.markdown(
        """
        Cleans an ADP Prior Payroll file so it can be ingested cleanly by downstream APIs.
        The cleaner does **two things and only two things**:

        1. **Merges duplicate pay-period rows** for the same employee (smart merge -- no double-counting).
        2. **Removes the grand-total row** at the bottom of the file, where the last employee's ID got bled into the totals row.

        Upload an `.xlsx` / `.xls` / `.csv`. The cleaned output is **always a `.csv`** with the **same column headers** as the input.
        """
    )

    file = st.file_uploader(
        "Upload ADP Prior Payroll File",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=False,
        key="pps_input",
    )

    if not file:
        return

    if not st.button("Run Sanity Check", type="primary", use_container_width=True):
        return

    try:
        with st.spinner("Reading and cleaning..."):
            df_in, header_idx, sheet = read_input_file(file)
            original_count = len(df_in)
            df_a, gt_info = detect_grand_total_row(df_in)
            df_b, merge_events = merge_duplicate_pay_periods(df_a)
            final_count = len(df_b)
    except Exception as e:
        st.error(f"Failed to process the file: {e}")
        return

    rows_removed = original_count - final_count

    st.success("Sanity check complete!")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Original Rows", original_count)
    m2.metric("Cleaned Rows", final_count)
    m3.metric("Grand Total Removed", "Yes" if gt_info else "No")
    m4.metric("Duplicate Groups Merged", len(merge_events))

    if gt_info:
        st.warning(
            "**Grand total row removed.** "
            f"It carried Employee ID `{gt_info['removed_employee_id']}` "
            f"({gt_info['removed_employee_name'] or 'name unknown'}). "
            f"Detected because column `{gt_info['matched_on_column']}` had value "
            f"`{gt_info['matched_value']:,.2f}` -- approximately the sum of all preceding rows "
            f"(`{gt_info['expected_sum']:,.2f}`)."
        )

    if merge_events:
        with st.expander(f"Merged duplicate pay-period rows ({len(merge_events)} groups)", expanded=False):
            st.dataframe(pd.DataFrame(merge_events), use_container_width=True, hide_index=True)
    else:
        st.info("No duplicate pay-period rows were found.")

    if not gt_info and not merge_events:
        st.info("No issues detected -- the file is already clean. Cleaned output is identical to input.")

    with st.expander(f"Preview cleaned data ({final_count} rows)", expanded=False):
        st.dataframe(df_b.head(50), use_container_width=True)

    csv_buf = io.StringIO()
    df_b.to_csv(csv_buf, index=False)

    base_name = file.name.rsplit(".", 1)[0]
    st.download_button(
        label="Download Cleaned CSV",
        data=csv_buf.getvalue(),
        file_name=f"{base_name}_cleaned.csv",
        mime="text/csv",
        key="pps_download",
        use_container_width=True,
    )


if __name__ == "__main__":
    st.set_page_config(page_title="ADP Prior Payroll Sanity Check", layout="wide")
    render_ui()
