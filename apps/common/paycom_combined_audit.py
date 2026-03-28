import streamlit as st
import pandas as pd
import numpy as np
import io
import re
from datetime import datetime, date
from utils.audit_utils import norm_col, norm_colname, norm_blank, try_parse_date, clean_money_val

# =========================================================
# Paycom Consolidated Audit Tool (Census, Payment, Emergency)
# =========================================================

APP_TITLE = "Paycom - Consolidated Audit (Census/Payment/Emergency)"

# --- Status Constants ---
STATUS_MATCH = "Data Match"
STATUS_MISMATCH = "Data Mismatch"
STATUS_VAL_MISSING_UZIO = "Value missing in Uzio"
STATUS_VAL_MISSING_PAYCOM = "Value missing in Paycom"
STATUS_MISSING_UZIO = "Employee ID Not Found in Uzio"
STATUS_MISSING_PAYCOM = "Employee ID Not Found in Paycom"

def norm_str(x):
    if pd.isna(x) or x is None:
        return ""
    return str(x).strip()

def norm_id(x):
    """Normalize Employee ID (remove .0, strip, lstrip zeros)."""
    if pd.isna(x): return ""
    s = str(x).strip()
    if s.endswith(".0"): s = s[:-2]
    return s.lstrip("0")

def norm_phone(x):
    """Normalize phone to just digits."""
    if pd.isna(x): return ""
    digits = re.sub(r"\D", "", str(x))
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    return digits

def norm_money(x):
    """Parse money/float safely."""
    if pd.isna(x) or x is None:
        return 0.0
    s = str(x).replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except:
        return 0.0

def norm_relation(x):
    """Normalize relationship (uppercase, strip)."""
    return str(x).strip().upper()

# --- Uzio Master Reader ---
def read_uzio_master(file):
    """
    Reads the Uzio Master CSV which has Category labels in Row 1 
    and actual Headers in Row 2.
    """
    # Read first two rows to build combined headers
    df_headers = pd.read_csv(io.StringIO(file.getvalue().decode('utf-8', errors='replace')), nrows=2, header=None)
    
    row1 = df_headers.iloc[0].fillna(method='ffill').tolist() # Categories
    row2 = df_headers.iloc[1].fillna('').tolist() # Headers
    
    # Combined headers for easy lookup
    combined_cols = []
    for c, h in zip(row1, row2):
        if h:
            combined_cols.append(f"{c}|{h}")
        else:
            combined_cols.append(c)
            
    # Read full data
    file.seek(0)
    df = pd.read_csv(file, skiprows=2, header=None, dtype=str)
    df.columns = combined_cols
    return df

# --- Field Mappings ---
PAYCOM_CENSUS_MAP = {
    "Personal|First Name": "Legal_Firstname",
    "Personal|Last Name": "Legal_Lastname",
    "Personal|SSN": "SSN",
    "Personal|Date Of Birth": "Birth_Date",
    "Personal|Gender": "Gender",
    "Job|Employee ID": "Employee_Code",
    "Job|Date of Hire": "Hire_Date",
    "Job|Employment Type": "Employment_Type_Desc",
    "Job|Pay Type": "Pay_Type",
    "Job|Annual Salary": "Annual_Salary",
    "Job|Hourly Rate": "Hourly_Rate",
    "Job|Job Title": "Job_Title_Desc",
    "Job|Department": "Department_Desc",
    "Home Address|Address Line 1": "Address_Line_1",
    "Home Address|Address Line 2": "Address_Line_2",
    "Home Address|City": "City",
    "Home Address|Zip": "Zip_Code",
    "Home Address|State": "State",
    "Additional Information|License Number": "DriversLicense",
    "Additional Information|License Expiration Date": "DLExpirationDate"
}

# --- Core Audit Logic (Ported from individual tools) ---

def run_census_audit(df_uzio, df_paycom):
    rows = []
    # Identify key columns
    u_id_col = "Job|Employee ID"
    p_id_col = next((c for c in df_paycom.columns if "Employee_Code" in c), "Employee_Code")
    
    u_map = {id: idx for idx, id in enumerate(df_uzio[u_id_col].map(norm_id))}
    p_map = {id: idx for idx, id in enumerate(df_paycom[p_id_col].map(norm_id))}
    
    all_ids = set(u_map.keys()) | set(p_map.keys())
    
    for eid in sorted(all_ids):
        u_idx = u_map.get(eid)
        p_idx = p_map.get(eid)
        
        if eid == "" or eid == "nan": continue
        
        name = ""
        if u_idx is not None:
            name = f"{df_uzio.at[u_idx, 'Personal|First Name']} {df_uzio.at[u_idx, 'Personal|Last Name']}"
        elif p_idx is not None:
            name = f"{df_paycom.at[p_idx, 'Legal_Firstname']} {df_paycom.at[p_idx, 'Legal_Lastname']}"

        for u_col, p_col in PAYCOM_CENSUS_MAP.items():
            u_val = ""
            p_val = ""
            status = STATUS_MATCH
            
            if u_idx is not None and u_col in df_uzio.columns:
                u_val = norm_str(df_uzio.at[u_idx, u_col])
            if p_idx is not None and p_col in df_paycom.columns:
                p_val = norm_str(df_paycom.at[p_idx, p_col])
                
            # Normalization/Comparison
            if "Date" in u_col or "Birth" in u_col:
                u_val = try_parse_date(u_val)
                p_val = try_parse_date(p_val)
            elif "SSN" in u_col or "Phone" in u_col or "Zip" in u_col:
                u_val = re.sub(r"\D", "", u_val)
                p_val = re.sub(r"\D", "", p_val)
                
            if u_idx is None: status = STATUS_MISSING_UZIO
            elif p_idx is None: status = STATUS_MISSING_PAYCOM
            elif u_val.lower() != p_val.lower():
                # Allow minor money diff
                if "Salary" in u_col or "Rate" in u_col:
                    try:
                        if abs(float(u_val or 0) - float(p_val or 0)) < 0.1:
                            status = STATUS_MATCH
                        else: status = STATUS_MISMATCH
                    except: status = STATUS_MISMATCH
                else:
                    status = STATUS_MISMATCH
            
            rows.append({
                "Employee ID": eid,
                "Employee Name": name,
                "Section": "Census",
                "Field": u_col.split("|")[-1],
                "Uzio Value": u_val,
                "Paycom Value": p_val,
                "Status": status
            })
    return pd.DataFrame(rows)

def run_payment_audit(df_uzio, df_paycom):
    # Uzio Master usually has one distribution per row? 
    # Or multiple rows per employee? 
    # Based on standard reports, Master Custom is often one row per record.
    # We will group by Employee ID.
    rows = []
    u_id_col = "Job|Employee ID"
    p_id_col = "Employee_Code"
    
    # Process Uzio Accounts
    u_accounts = {}
    for idx, row in df_uzio.iterrows():
        eid = norm_id(row.get(u_id_col))
        if not eid: continue
        
        acc = {
            "Routing": norm_phone(row.get("Payment Method|Routing Number")),
            "Account": norm_phone(row.get("Payment Method|Account Number")),
            "Type": norm_str(row.get("Payment Method|Account Type")).lower(),
            "Percent": norm_money(row.get("Payment Method|Paycheck Percentage")),
            "Amount": norm_money(row.get("Payment Method|Paycheck Amount")),
            "Name": f"{row.get('Personal|First Name')} {row.get('Personal|Last Name')}"
        }
        if acc["Routing"] or acc["Account"]:
            if eid not in u_accounts: u_accounts[eid] = []
            u_accounts[eid].append(acc)

    # Process Paycom Accounts (Unpivot 1-8 + Net)
    p_accounts = {}
    for idx, row in df_paycom.iterrows():
        eid = norm_id(row.get(p_id_col))
        if not eid: continue
        
        accs = []
        # Distributions 1-8
        for i in range(1, 9):
            prefix = f"Dist_{i}_"
            if f"{prefix}Acct_Code" in df_paycom.columns:
                d_acc = norm_phone(row.get(f"{prefix}Acct_Code"))
                d_rout = norm_phone(row.get(f"{prefix}Rout_Code"))
                if d_acc or d_rout:
                    accs.append({
                        "Routing": d_rout,
                        "Account": d_acc,
                        "Type": norm_str(row.get(f"{prefix}Type_Code")).lower(),
                        "Percent": norm_money(row.get(f"{prefix}Percent")),
                        "Amount": norm_money(row.get(f"{prefix}Amount")),
                        "IsNet": False
                    })
        # Net Account
        n_acc = norm_phone(row.get("Net_Acct_Code"))
        n_rout = norm_phone(row.get("Net_Rout_Code"))
        if n_acc or n_rout:
            accs.append({
                "Routing": n_rout,
                "Account": n_acc,
                "Type": norm_str(row.get("Net_Type_Code")).lower(),
                "Percent": 0.0, # Net handles remainder
                "Amount": 0.0,
                "IsNet": True
            })
        if accs:
            p_accounts[eid] = accs

    all_ids = set(u_accounts.keys()) | set(p_accounts.keys())
    for eid in sorted(all_ids):
        uas = u_accounts.get(eid, [])
        pas = p_accounts.get(eid, [])
        name = uas[0]["Name"] if uas else ""
        
        # Simple matching for payment accounts (Ported logic)
        matched_p = set()
        for u in uas:
            match = None
            for i, p in enumerate(pas):
                if i in matched_p: continue
                if u["Routing"] == p["Routing"] and u["Account"] == p["Account"]:
                    match = p
                    matched_p.add(i)
                    break
            
            if match:
                # Compare fields
                for f in ["Routing", "Account", "Type"]:
                    rows.append({
                        "Employee ID": eid, "Employee Name": name, "Section": "Payment",
                        "Field": f, "Uzio Value": u[f], "Paycom Value": match[f],
                        "Status": STATUS_MATCH if str(u[f]).strip().lower() == str(match[f]).strip().lower() else STATUS_MISMATCH
                    })
            else:
                rows.append({
                    "Employee ID": eid, "Employee Name": name, "Section": "Payment",
                    "Field": "Account", "Uzio Value": u["Account"], "Paycom Value": "Not Found",
                    "Status": STATUS_VAL_MISSING_PAYCOM
                })
        
        # Paycom unmatched
        for i, p in enumerate(pas):
            if i not in matched_p:
                rows.append({
                    "Employee ID": eid, "Employee Name": name, "Section": "Payment",
                    "Field": "Account", "Uzio Value": "Not Found", "Paycom Value": p["Account"],
                    "Status": STATUS_VAL_MISSING_UZIO
                })

    return pd.DataFrame(rows)

def run_emergency_audit(df_uzio, df_paycom):
    rows = []
    u_id_col = "Job|Employee ID"
    p_id_col = "Employee_Code"
    
    u_contacts = {}
    for idx, row in df_uzio.iterrows():
        eid = norm_id(row.get(u_id_col))
        if not eid: continue
        contact = {
            "Name": norm_str(row.get("Emergency Contact|Name")),
            "Relation": norm_relation(row.get("Emergency Contact|Relationship")),
            "Phone": norm_phone(row.get("Emergency Contact|Phone")),
            "EmpName": f"{row.get('Personal|First Name')} {row.get('Personal|Last Name')}"
        }
        if contact["Name"]:
            if eid not in u_contacts: u_contacts[eid] = []
            u_contacts[eid].append(contact)

    p_contacts = {}
    for idx, row in df_paycom.iterrows():
        eid = norm_id(row.get(p_id_col))
        if not eid: continue
        # Paycom usually has Emergency_1_* columns, but relationship might be missing in some exports
        name = norm_str(row.get("Emergency_1_Contact"))
        if name:
            contact = {
                "Name": name,
                "Relation": norm_relation(row.get("Emergency_1_Relationship", "")),
                "Phone": norm_phone(row.get("Emergency_1_Phone", ""))
            }
            p_contacts[eid] = [contact]

    all_ids = set(u_contacts.keys()) | set(p_contacts.keys())
    for eid in sorted(all_ids):
        ucs = u_contacts.get(eid, [])
        pcs = p_contacts.get(eid, [])
        emp_name = ucs[0]["EmpName"] if ucs else ""

        # Ported logic: match on Name
        matched_p = set()
        for u in ucs:
            match = None
            for i, p in enumerate(pcs):
                if i in matched_p: continue
                if u["Name"].lower() == p["Name"].lower():
                    match = p
                    matched_p.add(i)
                    break
            
            if match:
                for f in ["Name", "Relation", "Phone"]:
                    u_v = u[f]
                    p_v = match[f]
                    rows.append({
                        "Employee ID": eid, "Employee Name": emp_name, "Section": "Emergency",
                        "Field": f, "Uzio Value": u_v, "Paycom Value": p_v,
                        "Status": STATUS_MATCH if u_v.lower() == p_v.lower() else STATUS_MISMATCH
                    })
            else:
                    rows.append({
                        "Employee ID": eid, "Employee Name": emp_name, "Section": "Emergency",
                        "Field": "Contact Name", "Uzio Value": u["Name"], "Paycom Value": "Not Found",
                        "Status": STATUS_VAL_MISSING_PAYCOM
                    })

        # Paycom unmatched (Missing in Uzio)
        for i, p in enumerate(pcs):
            if i not in matched_p:
                rows.append({
                    "Employee ID": eid, "Employee Name": emp_name, "Section": "Emergency",
                    "Field": "Contact Name", "Uzio Value": "Not Found", "Paycom Value": p["Name"],
                    "Status": STATUS_VAL_MISSING_UZIO
                })
    return pd.DataFrame(rows)

# --- UI Functions ---
def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    This tool performs a consolidated audit of Census, Payment, and Emergency contact data 
    using the **Uzio Master Custom Report** and a **Paycom Census Export**.
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        u_file = st.file_uploader("Upload Uzio Master Report (CSV)", type=["csv"], key="comb_u")
    with col2:
        p_file = st.file_uploader("Upload Paycom Census Export (Excel/CSV)", type=["xlsx", "csv"], key="comb_p")

    client_name = st.text_input("Client Name", value="Falcon Logistics", key="comb_client")

    if st.button("Run Consolidated Audit", type="primary"):
        if not u_file or not p_file:
            st.error("Please upload both files.")
            return
            
        try:
            with st.spinner("Processing files..."):
                # Load Uzio
                df_uzio = read_uzio_master(u_file)
                
                # Load Paycom
                if p_file.name.endswith(".csv"):
                    df_paycom = pd.read_csv(p_file, dtype=str)
                else:
                    df_paycom = pd.read_excel(p_file, dtype=str)
                
                # Run Audits
                res_census = run_census_audit(df_uzio, df_paycom)
                res_payment = run_payment_audit(df_uzio, df_paycom)
                res_emergency = run_emergency_audit(df_uzio, df_paycom)
                
                # Combine
                all_results = pd.concat([res_census, res_payment, res_emergency], ignore_index=True)
                
                st.success("Audit complete!")
                
                # Download
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                    # Overall Summary
                    summary = all_results.groupby(["Section", "Status"]).size().reset_index(name="Count")
                    summary.to_excel(writer, sheet_name="Summary", index=False)
                    
                    # Detailed Sheets
                    res_census.to_excel(writer, sheet_name="Census_Audit", index=False)
                    res_payment.to_excel(writer, sheet_name="Payment_Audit", index=False)
                    res_emergency.to_excel(writer, sheet_name="Emergency_Audit", index=False)
                    
                timestamp = pd.Timestamp.now().strftime('%d_%m_%Y_%H%M')
                filename = f"{client_name}_Consolidated_Audit_Report_{timestamp}.xlsx"
                
                st.download_button(
                    label="Download Consolidated Report",
                    data=out.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

if __name__ == "__main__":
    render_ui()
