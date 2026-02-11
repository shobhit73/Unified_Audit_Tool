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

# --- Constants for Status ---
STATUS_MATCH = "Data Match"
STATUS_MISMATCH = "Data Mismatch"
STATUS_MISSING_UZIO = "Employee ID not found in the Uzio"
STATUS_MISSING_PAYCOM = "Employee ID not found in Paycom"

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

def strip_type(t):
    """Normalize account type string for comparison (Checking vs Checking Account)."""
    if not t: return ""
    return str(t).lower().replace("account", "").replace("Code: ", "").strip()

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

    # 2. Process Uzio Data (Long Format -> List of accounts per Emp)
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
            "Account": norm_digits(row.get(col_map["Account"])),
            "Type": norm_str(row.get(col_map["Type"])),
            "Percent": norm_money(row.get(col_map["Percent"])),
            "Amount": norm_money(row.get(col_map["Amount"])),
            "Source": "Uzio",
            "Name": norm_str(row.get(col_map["Name"]))
        }
        
        if acc["Routing"] or acc["Account"]:
            if emp_id not in uzio_map:
                uzio_map[emp_id] = []
            uzio_map[emp_id].append(acc)

    # 3. Process Paycom Data (Wide Format -> Unpivot)
    paycom_accounts = []
    df_paycom.columns = [str(c).strip() for c in df_paycom.columns]
    
    pc_empid_col = next((c for c in df_paycom.columns if "Employee_Code" in c or "Emp Code" in c), "Employee_Code")

    for idx, row in df_paycom.iterrows():
        emp_id = norm_str(row.get(pc_empid_col))
        if not emp_id: continue

        # --- Extract NET Pay Account ---
        net_acc = norm_digits(row.get("Net_Acct_Code"))
        net_rout = norm_digits(row.get("Net_Rout_Code"))
        if net_acc or net_rout:
             p_type = row.get("Net_Type_Code")
             paycom_accounts.append({
                 "EmpID": emp_id,
                 "Routing": net_rout,
                 "Account": net_acc,
                 "Type": str(p_type),
                 "Percent": 100.0,
                 "Amount": 0.0,
                 "IsNet": True
             })

        # --- Extract Distributions (1 to 8) ---
        for i in range(1, 9):
            prefix = f"Dist_{i}_"
            d_acc = norm_digits(row.get(f"{prefix}Acct_Code"))
            d_rout = norm_digits(row.get(f"{prefix}Rout_Code"))
            
            if d_acc or d_rout:
                d_type = row.get(f"{prefix}Type_Code")
                d_amt = norm_money(row.get(f"{prefix}Amount"))
                d_pct = norm_money(row.get(f"{prefix}Percent"))
                
                paycom_accounts.append({
                    "EmpID": emp_id,
                    "Routing": d_rout,
                    "Account": d_acc,
                    "Type": str(d_type),
                    "Percent": d_pct,
                    "Amount": d_amt,
                    "IsNet": False
                })

    # Group Paycom by EmpID
    paycom_map = {}
    for item in paycom_accounts:
        eid = item["EmpID"]
        if eid not in paycom_map:
            paycom_map[eid] = []
        paycom_map[eid].append(item)

    # 4. Comparison Logic
    report_rows = []
    all_emps = set(uzio_map.keys()) | set(paycom_map.keys())

    for emp_id in all_emps:
        u_accs = uzio_map.get(emp_id, [])
        p_accs = paycom_map.get(emp_id, [])
        
        emp_name = u_accs[0]["Name"] if u_accs else "Unknown (Paycom Only)"

        if not u_accs and p_accs:
            for p in p_accs:
                 report_rows.append({
                     "Employee ID": emp_id, "Employee Name": emp_name,
                     "Status": STATUS_MISSING_UZIO,
                     "Comparison Note": "",
                     "Uzio Routing": "", "Paycom Routing": p["Routing"],
                     "Uzio Account": "", "Paycom Account": p["Account"],
                     "Uzio Type": "", "Paycom Type": p["Type"],
                     "Uzio Amount": "", "Paycom Amount": p["Amount"],
                     "Uzio Percent": "", "Paycom Percent": p["Percent"]
                 })
            continue

        if u_accs and not p_accs:
            for u in u_accs:
                report_rows.append({
                     "Employee ID": emp_id, "Employee Name": u["Name"],
                     "Status": STATUS_MISSING_PAYCOM,
                     "Comparison Note": "",
                     "Uzio Routing": u["Routing"], "Paycom Routing": "",
                     "Uzio Account": u["Account"], "Paycom Account": "",
                     "Uzio Type": u["Type"], "Paycom Type": "",
                     "Uzio Amount": u["Amount"], "Paycom Amount": "",
                     "Uzio Percent": u["Percent"], "Paycom Percent": ""
                 })
            continue

        # Both exist - Compare Account sets
        p_remaining = p_accs.copy()
        
        for u in u_accs:
            match = None
            for p in p_remaining:
                if u["Routing"] == p["Routing"] and u["Account"] == p["Account"]:
                    match = p
                    break
            
            if match:
                p_remaining.remove(match)
                issues = []
                if strip_type(u["Type"]) != strip_type(match["Type"]):
                     issues.append(f"Type Mismatch ({u['Type']} vs {match['Type']})")
                if u["Amount"] > 0:
                    if abs(u["Amount"] - match["Amount"]) > 0.01:
                         issues.append(f"Amount Mismatch ({u['Amount']} vs {match['Amount']})")
                elif u["Percent"] > 0:
                    if abs(u["Percent"] - match["Percent"]) > 0.1:
                         issues.append(f"Percent Mismatch ({u['Percent']} vs {match['Percent']})")

                status = STATUS_MISMATCH if issues else STATUS_MATCH
                note = "; ".join(issues)

                report_rows.append({
                     "Employee ID": emp_id, "Employee Name": u["Name"],
                     "Status": status, "Comparison Note": note,
                     "Uzio Routing": u["Routing"], "Paycom Routing": match["Routing"],
                     "Uzio Account": u["Account"], "Paycom Account": match["Account"],
                     "Uzio Type": u["Type"], "Paycom Type": match["Type"],
                     "Uzio Amount": u["Amount"], "Paycom Amount": match["Amount"],
                     "Uzio Percent": u["Percent"], "Paycom Percent": match["Percent"]
                 })
            else:
                report_rows.append({
                     "Employee ID": emp_id, "Employee Name": u["Name"],
                     "Status": STATUS_MISMATCH,
                     "Comparison Note": "Account in Uzio not found in Paycom",
                     "Uzio Routing": u["Routing"], "Paycom Routing": "Not Found",
                     "Uzio Account": u["Account"], "Paycom Account": "Not Found",
                     "Uzio Type": u["Type"], "Paycom Type": "",
                     "Uzio Amount": u["Amount"], "Paycom Amount": "",
                     "Uzio Percent": u["Percent"], "Paycom Percent": ""
                 })

        for p in p_remaining:
             report_rows.append({
                 "Employee ID": emp_id, "Employee Name": emp_name,
                 "Status": STATUS_MISMATCH,
                 "Comparison Note": "Account in Paycom not found in Uzio",
                 "Uzio Routing": "Not Found", "Paycom Routing": p["Routing"],
                 "Uzio Account": "Not Found", "Paycom Account": p["Account"],
                 "Uzio Type": "", "Paycom Type": p["Type"],
                 "Uzio Amount": "", "Paycom Amount": p["Amount"],
                 "Uzio Percent": "", "Paycom Percent": p["Percent"]
             })

    # 5. Generate Output (Consistent with census_audit_app.py)
    df_report = pd.DataFrame(report_rows)
    
    cols_order = [
        "Employee ID", "Employee Name", "Status", "Comparison Note",
        "Uzio Routing", "Paycom Routing",
        "Uzio Account", "Paycom Account",
        "Uzio Amount", "Paycom Amount",
        "Uzio Percent", "Paycom Percent",
        "Uzio Type", "Paycom Type"
    ]
    final_cols = [c for c in cols_order if c in df_report.columns]
    comparison_detail = df_report[final_cols]

    # ---------- Summary metrics ----------
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
            len(uzio_map),
            len(paycom_map),
            len(set(uzio_map.keys()) & set(paycom_map.keys())),
            len(set(uzio_map.keys()) - set(paycom_map.keys())),
            len(set(paycom_map.keys()) - set(uzio_map.keys())),
            comparison_detail.shape[0],
            comparison_detail[comparison_detail["Status"] != STATUS_MATCH].shape[0]
        ]
    })

    # ---------- Export report ----------
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        comparison_detail.to_excel(writer, sheet_name="Comparison_Detail_AllFields", index=False)

    return out.getvalue()
