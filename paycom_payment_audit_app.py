import streamlit as st
import pandas as pd
import numpy as np
import io
import re
from datetime import datetime, date

# =========================================================
# Paycom vs Uzio Payment Audit Tool
# =========================================================

APP_TITLE = "Paycom vs Uzio – Payment Audit Tool"

# --- Constants for Status (8 statuses, matching census_audit_app.py) ---
STATUS_MATCH = "Data Match"
STATUS_MISMATCH = "Data Mismatch"
STATUS_VAL_MISSING_UZIO = "Value missing in Uzio (Paycom has value)"
STATUS_VAL_MISSING_PAYCOM = "Value missing in Paycom (Uzio has value)"
STATUS_MISSING_UZIO = "Employee ID Not Found in Uzio"
STATUS_MISSING_PAYCOM = "Employee ID Not Found in Paycom"
STATUS_COL_MISSING_PAYCOM = "Column Missing in Paycom Sheet"
STATUS_COL_MISSING_UZIO = "Column Missing in Uzio Sheet"

def norm_str(x):
    if x is None:
        return ""
    return str(x).strip()

def norm_digits(x):
    """Keep only digits, remove spaces/dashes."""
    if x is None:
        return ""
    if isinstance(x, (float, int)):
        if pd.isna(x):
            return ""
        return str(int(x))
    return re.sub(r"\D", "", str(x))

def norm_money(x):
    """Parse money/float safely."""
    if x is None:
        return 0.0
    if isinstance(x, (float, int)):
        return 0.0 if pd.isna(x) else float(x)
    s = str(x).replace(",", "").replace("$", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except:
        return 0.0

# Paycom uses numeric type codes; map them to human-readable names
_TYPE_CODE_MAP = {
    "22": "checking",
    "32": "savings",
    "1": "checking",   # Net_Type_Code sometimes uses 1 for checking
    "2": "checking",   # Sometimes Paycom uses 2 or 2.0 for checking
}

def strip_type(t):
    """Normalize account type string for comparison.
    Handles Paycom numeric codes: 22=Checking, 32=Savings."""
    if not t: return ""
    s = str(t).strip()
    # Remove trailing ".0" from float-read values like "22.0"
    if s.endswith(".0"):
        s = s[:-2]
    # Check if it's a known Paycom type code
    if s in _TYPE_CODE_MAP:
        return _TYPE_CODE_MAP[s]
    return s.lower().replace("account", "").replace("code: ", "").strip()

# ---------- Minimal UI (Consistent with census_audit_app.py) ----------
def render_ui():
    st.title(APP_TITLE)
    st.write("Upload the Excel workbook (.xlsx). The tool will generate the audit report and provide a download button.")

    uploaded_file = st.file_uploader("Upload Excel workbook", type=["xlsx"])
    run_btn = st.button("Run Audit", type="primary", disabled=(uploaded_file is None))

    if run_btn:
        try:
            with st.spinner("Running audit..."):
                report_bytes = run_audit(uploaded_file)

            st.success("Report generated.")

            today_str = date.today().isoformat()
            out_filename = f"Client_Name_Paycom_Payment_Data_Audit_{today_str}.xlsx"

            st.download_button(
                label="Download Report (.xlsx)",
                data=report_bytes,
                file_name=out_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )
        except Exception as e:
            st.error(f"Failed: {e}")

# ---------- Core Audit Logic ----------
def run_audit(file_obj):
    # 1. Load Data
    xl = pd.ExcelFile(file_obj)
    
    req_sheets = ["Uzio Data", "Paycom Data"]
    for s in req_sheets:
        if s not in xl.sheet_names:
            raise ValueError(f"Missing sheet: {s}")

    df_uzio = pd.read_excel(xl, "Uzio Data")
    df_paycom = pd.read_excel(xl, "Paycom Data")

    # 2. Process Uzio Data
    df_uzio.columns = [str(c).strip() for c in df_uzio.columns]
    
    col_map = {
        "EmpID": next((c for c in df_uzio.columns if "Employee ID" in c), "Employee ID"),
        "Routing": next((c for c in df_uzio.columns if "Routing" in c), "Routing Number"),
        "Account": next((c for c in df_uzio.columns if "Account Nu" in c), "Account Number"),
        "Type": next((c for c in df_uzio.columns if "Account Type" in c), "Account Type"),
        "Percent": next((c for c in df_uzio.columns if "Percent" in c), "Paycheck Percentage"),
        "Amount": next((c for c in df_uzio.columns if "Amount" in c), "Paycheck Amount"),
        "Name": next((c for c in df_uzio.columns if "Full Name" in c), "Full Name")
    }

    uzio_map = {}
    
    for idx, row in df_uzio.iterrows():
        emp_id = norm_str(row.get(col_map["EmpID"]))
        if not emp_id: continue
        
        acc = {
            "Routing": norm_digits(row.get(col_map["Routing"])),
            "Account": norm_digits(row.get(col_map["Account"])).lstrip("0"),
            "Type": norm_str(row.get(col_map["Type"])),
            "Percent": norm_money(row.get(col_map["Percent"])),
            "Amount": norm_money(row.get(col_map["Amount"])),
            "Name": norm_str(row.get(col_map["Name"]))
        }
        
        if acc["Routing"] or acc["Account"]:
            if emp_id not in uzio_map:
                uzio_map[emp_id] = []
            
            # Deduplicate: Only add if this exact account isn't already listed for this employee
            if acc not in uzio_map[emp_id]:
                uzio_map[emp_id].append(acc)

    # 3. Process Paycom Data (Wide Format -> Unpivot)
    paycom_accounts = []
    df_paycom.columns = [str(c).strip() for c in df_paycom.columns]
    
    pc_empid_col = next((c for c in df_paycom.columns if "Employee_Code" in c or "Emp Code" in c), "Employee_Code")

    for idx, row in df_paycom.iterrows():
        emp_id = norm_str(row.get(pc_empid_col))
        if not emp_id: continue

        # --- Extract Distributions (1 to 8) FIRST, so we can sum percents ---
        dist_entries = []
        total_dist_pct = 0.0
        total_dist_amt = 0.0

        for i in range(1, 9):
            prefix = f"Dist_{i}_"
            d_acc = norm_digits(row.get(f"{prefix}Acct_Code")).lstrip("0")
            d_rout = norm_digits(row.get(f"{prefix}Rout_Code"))
            
            if d_acc or d_rout:
                d_type = row.get(f"{prefix}Type_Code")
                raw_amt = row.get(f"{prefix}Amount")
                d_amt = norm_money(raw_amt)
                d_pct = 0.0

                # Check for a dedicated Percent column first
                pct_col = f"{prefix}Percent"
                if pct_col in df_paycom.columns:
                    d_pct = norm_money(row.get(pct_col))

                # Detect percentage in Amount field:
                #   - String contains "%" (e.g. "25%")
                #   - Excel percentage format (0 < value <= 1.0 stored as decimal)
                if d_pct == 0.0 and d_amt != 0.0:
                    raw_str = str(raw_amt).strip() if raw_amt is not None else ""
                    if "%" in raw_str:
                        # Explicit "%" in the string, e.g. "25%" or "99%"
                        try:
                            d_pct = float(raw_str.replace("%", "").replace(",", "").strip())
                        except:
                            d_pct = 0.0
                        d_amt = 0.0
                    elif 0 < abs(d_amt) <= 1.0:
                        # Excel reads 25% as 0.25 — scale up to percentage
                        d_pct = round(d_amt * 100, 4)
                        d_amt = 0.0

                total_dist_pct += d_pct
                total_dist_amt += d_amt

                dist_entries.append({
                    "EmpID": emp_id,
                    "Routing": d_rout,
                    "Account": d_acc,
                    "Type": str(d_type) if d_type is not None else "",
                    "Percent": d_pct,
                    "Amount": d_amt,
                    "IsNet": False
                })

        paycom_accounts.extend(dist_entries)

        # --- Extract NET Pay Account (remainder after distributions) ---
        net_acc = norm_digits(row.get("Net_Acct_Code")).lstrip("0")
        net_rout = norm_digits(row.get("Net_Rout_Code"))
        if net_acc or net_rout:
             p_type = row.get("Net_Type_Code")
             
             # Calculate Net Percent:
             # Case 1: Partial Percentage Dists -> Net is remainder (100 - total)
             if total_dist_pct > 0:
                 net_pct = round(100.0 - total_dist_pct, 4)
             # Case 2: Flat Dollar Dists (no %) -> Net is just "Remainder" (usually 0% or handled as amount)
             elif total_dist_amt > 0:
                 net_pct = 0.0
             # Case 3: No distributions -> 100% Net Pay
             else:
                 net_pct = 100.0

             paycom_accounts.append({
                 "EmpID": emp_id,
                 "Routing": net_rout,
                 "Account": net_acc,
                 "Type": str(p_type) if p_type is not None else "",
                 "Percent": net_pct,
                 "Amount": 0.0,
                 "IsNet": True
             })

    # Group Paycom by EmpID
    paycom_map = {}
    for item in paycom_accounts:
        eid = item["EmpID"]
        if eid not in paycom_map:
            paycom_map[eid] = []
        
        # Deduplicate: Only add if unique
        if item not in paycom_map[eid]:
            paycom_map[eid].append(item)

    # 4. Comparison Logic — Long Format (one row per field per account)
    # Fields to compare: Routing Number, Account Number, Account Type, Amount, Percent
    FIELDS = ["Routing Number", "Account Number", "Account Type", "Amount", "Percent"]

    rows = []
    all_emps = set(uzio_map.keys()) | set(paycom_map.keys())

    for emp_id in sorted(all_emps):
        u_accs = uzio_map.get(emp_id, [])
        p_accs = paycom_map.get(emp_id, [])
        
        emp_name = u_accs[0]["Name"] if u_accs else ""

        # --- Case: Missing in Uzio ---
        if not u_accs and p_accs:
            for p in p_accs:
                for field in FIELDS:
                    p_val = _get_field_val(p, field)
                    rows.append({
                        "Employee ID": emp_id,
                        "Employee Name": emp_name,
                        "Field": field,
                        "UZIO_Value": "",
                        "Paycom_Value": p_val,
                        "Paycom_SourceOfTruth_Status": STATUS_MISSING_UZIO
                    })
            continue

        # --- Case: Missing in Paycom ---
        if u_accs and not p_accs:
            for u in u_accs:
                for field in FIELDS:
                    u_val = _get_field_val(u, field)
                    rows.append({
                        "Employee ID": emp_id,
                        "Employee Name": u["Name"],
                        "Field": field,
                        "UZIO_Value": u_val,
                        "Paycom_Value": "",
                        "Paycom_SourceOfTruth_Status": STATUS_MISSING_PAYCOM
                    })
            continue

        # --- Case: Both exist — Match accounts (two-pass strategy) ---
        p_remaining = list(p_accs)
        u_unmatched = []

        # Pass 1: Exact match on Routing + Account
        for u in u_accs:
            match = None
            for p in p_remaining:
                if u["Routing"] == p["Routing"] and u["Account"] == p["Account"]:
                    match = p
                    break
            if match:
                p_remaining.remove(match)
                for field in FIELDS:
                    u_val = _get_field_val(u, field)
                    p_val = _get_field_val(match, field)
                    status = _compare_field(field, u_val, p_val, u, match)
                    rows.append({
                        "Employee ID": emp_id,
                        "Employee Name": u["Name"],
                        "Field": field,
                        "UZIO_Value": u_val,
                        "Paycom_Value": p_val,
                        "Paycom_SourceOfTruth_Status": status
                    })
            else:
                u_unmatched.append(u)

        # Pass 2: Fallback match on Routing + Account Type
        # (handles Paycom exports where account numbers lost precision)
        still_unmatched = []
        for u in u_unmatched:
            match = None
            u_type = strip_type(u["Type"])
            for p in p_remaining:
                if u["Routing"] == p["Routing"] and u_type and u_type == strip_type(p["Type"]):
                    match = p
                    break
            if match:
                p_remaining.remove(match)
                for field in FIELDS:
                    u_val = _get_field_val(u, field)
                    p_val = _get_field_val(match, field)
                    status = _compare_field(field, u_val, p_val, u, match)
                    rows.append({
                        "Employee ID": emp_id,
                        "Employee Name": u["Name"],
                        "Field": field,
                        "UZIO_Value": u_val,
                        "Paycom_Value": p_val,
                        "Paycom_SourceOfTruth_Status": status
                    })
            else:
                still_unmatched.append(u)

        # Pass 3: Fallback match on Routing Number ONLY (Last Resort)
        # (For cases like A00Z: Routing matches, but Account# precision lost AND Type code mismatch/unknown)
        final_unmatched = []
        for u in still_unmatched:
            match = None
            u_rout = u["Routing"]
            for p in p_remaining:
                # If routing matches, we assume it's the same account bank-wise
                # This prioritizes Routing Number as the primary key if all else fails
                if u_rout and u_rout == p["Routing"]:
                    match = p
                    break
            
            if match:
                p_remaining.remove(match)
                for field in FIELDS:
                    u_val = _get_field_val(u, field)
                    p_val = _get_field_val(match, field)
                    status = _compare_field(field, u_val, p_val, u, match)
                    rows.append({
                        "Employee ID": emp_id,
                        "Employee Name": u["Name"],
                        "Field": field,
                        "UZIO_Value": u_val,
                        "Paycom_Value": p_val,
                        "Paycom_SourceOfTruth_Status": status
                    })
            else:
                final_unmatched.append(u)

        # Uzio accounts that couldn't match at all
        for u in final_unmatched:
            for field in FIELDS:
                u_val = _get_field_val(u, field)
                rows.append({
                    "Employee ID": emp_id,
                    "Employee Name": u["Name"],
                    "Field": field,
                    "UZIO_Value": u_val,
                    "Paycom_Value": "Not Found",
                    "Paycom_SourceOfTruth_Status": STATUS_MISMATCH
                })

        # Paycom accounts unmatched
        for p in p_remaining:
            for field in FIELDS:
                p_val = _get_field_val(p, field)
                rows.append({
                    "Employee ID": emp_id,
                    "Employee Name": emp_name,
                    "Field": field,
                    "UZIO_Value": "Not Found",
                    "Paycom_Value": p_val,
                    "Paycom_SourceOfTruth_Status": STATUS_MISMATCH
                })

    # ---------- Build Output DataFrames ----------
    comparison_detail = pd.DataFrame(rows)[[
        "Employee ID", "Employee Name", "Field",
        "UZIO_Value", "Paycom_Value", "Paycom_SourceOfTruth_Status"
    ]]

    mismatches_only = comparison_detail[
        comparison_detail["Paycom_SourceOfTruth_Status"] != STATUS_MATCH
    ].copy()

    # ---------- Field Summary By Status ----------
    status_cols = [
        STATUS_MATCH,
        STATUS_MISMATCH,
        STATUS_VAL_MISSING_UZIO,
        STATUS_VAL_MISSING_PAYCOM,
        STATUS_MISSING_UZIO,
        STATUS_MISSING_PAYCOM,
        STATUS_COL_MISSING_PAYCOM,
        STATUS_COL_MISSING_UZIO,
    ]

    pivot = comparison_detail.pivot_table(
        index="Field",
        columns="Paycom_SourceOfTruth_Status",
        values="Employee ID",
        aggfunc="count",
        fill_value=0
    )

    for c in status_cols:
        if c not in pivot.columns:
            pivot[c] = 0

    pivot["Total"] = pivot.sum(axis=1)
    pivot[STATUS_MATCH] = pivot[STATUS_MATCH].astype(int)

    field_summary_by_status = pivot.reset_index()[[
        "Field", "Total",
        STATUS_MATCH, STATUS_MISMATCH,
        STATUS_VAL_MISSING_UZIO,
        STATUS_VAL_MISSING_PAYCOM,
        STATUS_MISSING_UZIO, STATUS_MISSING_PAYCOM,
        STATUS_COL_MISSING_PAYCOM, STATUS_COL_MISSING_UZIO,
    ]]

    # ---------- Summary metrics ----------
    uzio_keys = set(uzio_map.keys())
    paycom_keys = set(paycom_map.keys())

    summary = pd.DataFrame({
        "Metric": [
            "Employees in Uzio sheet",
            "Employees in Paycom sheet",
            "Employees present in both",
            "Employees missing in Paycom (Uzio only)",
            "Employees missing in Uzio (Paycom only)",
            "Total comparison rows",
            "Total NOT OK rows"
        ],
        "Value": [
            len(uzio_keys),
            len(paycom_keys),
            len(uzio_keys & paycom_keys),
            len(uzio_keys - paycom_keys),
            len(paycom_keys - uzio_keys),
            comparison_detail.shape[0],
            mismatches_only.shape[0]
        ]
    })

    # ---------- Export report (3 sheets like census_audit_app.py) ----------
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        field_summary_by_status.to_excel(writer, sheet_name="Field_Summary_By_Status", index=False)
        comparison_detail.to_excel(writer, sheet_name="Comparison_Detail_AllFields", index=False)

    return out.getvalue()


# ---------- Helper: Extract field value from account dict ----------
def _get_field_val(acc, field):
    mapping = {
        "Routing Number": "Routing",
        "Account Number": "Account",
        "Account Type": "Type",
        "Amount": "Amount",
        "Percent": "Percent"
    }
    val = acc.get(mapping.get(field, ""), "")
    return str(val) if val != "" else ""


# ---------- Helper: Compare a single field ----------
def _compare_field(field, u_val, p_val, u_acc, p_acc):
    u_n = str(u_val).strip() if u_val else ""
    p_n = str(p_val).strip() if p_val else ""

    # Both blank
    if u_n == "" and p_n == "":
        return STATUS_MATCH
    # One blank
    if u_n == "" and p_n != "":
        return STATUS_VAL_MISSING_UZIO
    if u_n != "" and p_n == "":
        return STATUS_VAL_MISSING_PAYCOM

    # Field-specific comparison
    if field == "Account Type":
        if strip_type(u_n) == strip_type(p_n):
            return STATUS_MATCH
        return STATUS_MISMATCH
    
    if field in ("Amount", "Percent"):
        try:
            diff = abs(float(u_n) - float(p_n))
            if diff < 0.01:
                return STATUS_MATCH
            # Special: both are 0, match
            if float(u_n) == 0.0 and float(p_n) == 0.0:
                return STATUS_MATCH
        except ValueError:
            pass
        return STATUS_MISMATCH

    # Default: exact string match (Routing, Account)
    if u_n == p_n:
        return STATUS_MATCH
    return STATUS_MISMATCH
