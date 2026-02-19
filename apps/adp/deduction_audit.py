import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

# =========================================================
# ADP to Uzio Deduction Audit Tool
# INPUT: One Excel File with 3 Tabs:
#   1. Uzio Data
#   2. ADP Data
#   3. Mapping Sheet
# =========================================================

def norm_col(c):
    """Normalize column names to be case-insensitive and stripped."""
    if c is None: return ""
    return str(c).strip().replace("\n", " ").strip()

def clean_money_val(x):
    """Parse money/percentage strings to float. Returns original string if not a number."""
    if pd.isna(x) or x == "":
        return 0.0
    s = str(x).strip()
    s_clean = s.replace("$", "").replace("%", "").replace(",", "")
    s_clean = s_clean.replace("(", "-").replace(")", "") # Handle accounting negative
    try:
        return float(s_clean)
    except:
        # If it's not a number (like an SSN), return the string itself for comparison
        return s

def run_audit(file_bytes):
    # Load Workbook
    xls = pd.ExcelFile(io.BytesIO(file_bytes), engine='openpyxl')
    
    # 1. Identify Sheets
    sheet_map = {norm_col(s).lower(): s for s in xls.sheet_names}
    
    # Helper to find sheet by keywords
    def get_sheet(keywords):
        for k, real_name in sheet_map.items():
            if any(kw in k for kw in keywords):
                return real_name
        return None

    uzio_sheet = get_sheet(["uzio"])
    adp_sheet = get_sheet(["adp", "prior", "payroll"])
    map_sheet = get_sheet(["mapping", "map"])

    if not all([uzio_sheet, adp_sheet, map_sheet]):
        missing = []
        if not uzio_sheet: missing.append("Uzio Data")
        if not adp_sheet: missing.append("ADP Data")
        if not map_sheet: missing.append("Mapping Sheet")
        return None, f"Missing Tabs: {', '.join(missing)}", []

    # 2. Read Data
    df_uzio = pd.read_excel(xls, sheet_name=uzio_sheet, dtype=str)
    df_adp = pd.read_excel(xls, sheet_name=adp_sheet, dtype=str)
    df_map = pd.read_excel(xls, sheet_name=map_sheet, dtype=str)

    return _run_deduction_audit(df_uzio, df_adp, df_map)

def _run_deduction_audit(df_uzio, df_adp, df_map):
    # Normalize Columns
    df_uzio.columns = [norm_col(c) for c in df_uzio.columns]
    df_adp.columns = [norm_col(c) for c in df_adp.columns]
    df_map.columns = [norm_col(c) for c in df_map.columns]

    # Process Mapping
    map_adp_col = next((c for c in df_map.columns if "adp" in c.lower()), None)
    map_uzio_col = next((c for c in df_map.columns if "uzio" in c.lower()), None)
    
    if not map_adp_col or not map_uzio_col:
        return None, "Mapping Sheet must have columns identifying 'ADP' and 'Uzio' deductions.", []

    mapping = {}
    for _, row in df_map.iterrows():
        k = str(row[map_adp_col]).strip()
        v = str(row[map_uzio_col]).strip()
        if k and v and k.lower() != 'nan' and v.lower() != 'nan':
            mapping[k] = v
            mapping[k.lower()] = v

    # Required Cols
    adp_id_col = next((c for c in df_adp.columns if "associate" in c.lower() and "id" in c.lower()), None)
    adp_code_col = next((c for c in df_adp.columns if "deduction" in c.lower() and "code" in c.lower()), None)
    adp_amt_col = next((c for c in df_adp.columns if "amount" in c.lower() or "rate" in c.lower()), None)
    adp_desc_col = next((c for c in df_adp.columns if "deduction" in c.lower() and "description" in c.lower()), None)
    adp_pct_col = next((c for c in df_adp.columns if "deduction" in c.lower() and "%" in c.lower()), None)

    if not all([adp_id_col, adp_code_col, adp_amt_col]):
        return None, f"ADP Sheet missing required columns (Associate ID, Deduction Code, Deduction Amount). Found: {list(df_adp.columns)}", []

    adp_records = []
    for _, row in df_adp.iterrows():
        emp_id = str(row[adp_id_col]).strip()
        raw_code = str(row[adp_code_col]).strip()
        raw_desc = str(row[adp_desc_col]).strip() if adp_desc_col else ""
        
        deduction_name = None
        if raw_desc:
            deduction_name = mapping.get(raw_desc, mapping.get(raw_desc.lower()))
        if not deduction_name and raw_code:
            deduction_name = mapping.get(raw_code, mapping.get(raw_code.lower()))
            
        if not deduction_name:
            continue
        
        amt = clean_money_val(row[adp_amt_col])
        if amt == 0.0 and adp_pct_col:
            pct_val = clean_money_val(row[adp_pct_col])
            if pct_val != 0.0:
                amt = pct_val
        
        adp_records.append({
            "Employee_ID": emp_id,
            "Deduction_Name": deduction_name,
            "ADP_Raw_Code": raw_code,
            "ADP_Description": raw_desc,
            "ADP_Amount": amt,
            "Key": f"{emp_id}|{deduction_name}".lower()
        })
    
    df_adp_clean = pd.DataFrame(adp_records)
    if not df_adp_clean.empty:
        df_adp_clean = df_adp_clean.groupby(["Employee_ID", "Deduction_Name", "ADP_Raw_Code", "ADP_Description", "Key"], as_index=False)["ADP_Amount"].sum()
    else:
        df_adp_clean = pd.DataFrame(columns=["Employee_ID", "Deduction_Name", "ADP_Raw_Code", "ADP_Description", "Key", "ADP_Amount"])

    # Process Uzio
    uz_id_col = next((c for c in df_uzio.columns if "employee" in c.lower() and "id" in c.lower()), None)
    uz_ded_col = next((c for c in df_uzio.columns if "deduction" in c.lower() and "name" in c.lower()), None)
    uz_amt_col = next((c for c in df_uzio.columns if "amount" in c.lower() or "percent" in c.lower()), None)

    if not all([uz_id_col, uz_ded_col, uz_amt_col]):
        return None, f"Uzio Sheet missing required columns (Employee ID, Deduction Name, Amount/Percentage). Found: {list(df_uzio.columns)}", []

    uzio_records = []
    for _, row in df_uzio.iterrows():
        emp_id = str(row[uz_id_col]).strip()
        ded_name = str(row[uz_ded_col]).strip()
        amt = clean_money_val(row[uz_amt_col])
        
        uzio_records.append({
            "Uzio_Employee_ID": emp_id,
            "Uzio_Deduction_Name": ded_name,
            "Uzio_Amount": amt,
            "Key": f"{emp_id}|{ded_name}".lower()
        })
    
    df_uz_clean = pd.DataFrame(uzio_records)
    if not df_uz_clean.empty:
        df_uz_clean = df_uz_clean.groupby(["Uzio_Employee_ID", "Uzio_Deduction_Name", "Key"], as_index=False)["Uzio_Amount"].sum()
    else:
        df_uz_clean = pd.DataFrame(columns=["Uzio_Employee_ID", "Uzio_Deduction_Name", "Key", "Uzio_Amount"])

    # Merge
    merged = pd.merge(df_adp_clean, df_uz_clean, on="Key", how="outer", suffixes=('_ADP', '_UZIO'))
    
    # IDs lists
    adp_emps = set(df_adp_clean["Employee_ID"].unique()) if not df_adp_clean.empty else set()
    uzio_emps = set(df_uz_clean["Uzio_Employee_ID"].unique()) if not df_uz_clean.empty else set()
    
    results = []
    for _, row in merged.iterrows():
        emp_id = row["Employee_ID"] if pd.notna(row["Employee_ID"]) else row["Uzio_Employee_ID"]
        
        adp_final_name = row["ADP_Description"] if pd.notna(row["ADP_Amount"]) and pd.notna(row["ADP_Description"]) else (row["ADP_Raw_Code"] if pd.notna(row["ADP_Amount"]) else "Not Available")
        uzio_final_name = row["Uzio_Deduction_Name"] if pd.notna(row["Uzio_Amount"]) else "Not Available"
        
        raw_code = row["ADP_Raw_Code"] if pd.notna(row["ADP_Raw_Code"]) else ""
        adp_val = row["ADP_Amount"] if pd.notna(row["ADP_Amount"]) else 0.0
        uz_val = row["Uzio_Amount"] if pd.notna(row["Uzio_Amount"]) else 0.0
        
        has_adp = pd.notna(row["ADP_Amount"])
        has_uzio = pd.notna(row["Uzio_Amount"])
        
        status = ""
        if has_adp and has_uzio:
            if abs(adp_val - uz_val) < 0.01:
                status = "Data Match"
            else:
                status = "Data Mismatch"
        elif has_adp and not has_uzio:
            if emp_id in uzio_emps:
                status = "Value missing in Uzio (ADP has value)"
            else:
                status = "Employee ID Not Found in Uzio"
        elif has_uzio and not has_adp:
            if emp_id in adp_emps:
                status = "Value missing in ADP (Uzio has value)"
            else:
                status = "Employee ID Not Found in ADP"
        
        results.append({
            "Employee ID": emp_id,
            "ADP Deduction Description": adp_final_name,
            "Uzio Deduction Name": uzio_final_name,
            "ADP Code": raw_code,
            "ADP Amount": adp_val,
            "Uzio Amount": uz_val,
            "Status": status
        })
        
    return _generate_output(results)

def _generate_output(results):
    df_res = pd.DataFrame(results)
    
    # Consolidate Field Logic for Deduction Audit
    def get_field_name(row):
        uz_name = row.get("Uzio Deduction Name", "Not Available")
        adp_name = row.get("ADP Deduction Description", "Not Available")
        
        if uz_name != "Not Available":
            return uz_name
        return adp_name

    df_res["Field"] = df_res.apply(get_field_name, axis=1)

    # Pivot Summary
    expected_statuses = [
        "Data Match", "Data Mismatch", 
        "Value missing in Uzio (ADP has value)", "Value missing in ADP (Uzio has value)", 
        "Employee ID Not Found in Uzio", "Employee ID Not Found in ADP",
        "Column Missing in ADP Sheet", "Column Missing in Uzio Sheet"
    ]
    
    if not df_res.empty:
        field_summary = df_res.groupby(["Field", "Status"]).size().unstack(fill_value=0)
    else:
        field_summary = pd.DataFrame()

    for col in expected_statuses:
        if col not in field_summary.columns:
            field_summary[col] = 0
            
    field_summary["Total"] = field_summary.sum(axis=1) if not field_summary.empty else 0
    
    # Reorder
    cols_order = ["Total"] + [c for c in expected_statuses if c in field_summary.columns] + [c for c in field_summary.columns if c not in expected_statuses and c != "Total"]
    field_summary = field_summary[cols_order]
    
    out_buffer = io.BytesIO()
    with pd.ExcelWriter(out_buffer, engine='openpyxl') as writer:
        summary_data = {
            "Total Records": [len(df_res)],
            "Matches": [len(df_res[df_res["Status"] == "Data Match"])] if not df_res.empty else [0],
            "Mismatches": [len(df_res[df_res["Status"] == "Data Mismatch"])] if not df_res.empty else [0],
            "Value Missing in Uzio": [len(df_res[df_res["Status"] == "Value missing in Uzio (ADP has value)"])] if not df_res.empty else [0],
            "Emp Missing in Uzio": [len(df_res[df_res["Status"] == "Employee ID Not Found in Uzio"])] if not df_res.empty else [0],
             "Value Missing in ADP": [len(df_res[df_res["Status"] == "Value missing in ADP (Uzio has value)"])] if not df_res.empty else [0],
            "Emp Missing in ADP": [len(df_res[df_res["Status"] == "Employee ID Not Found in ADP"])] if not df_res.empty else [0]
        }
        pd.DataFrame(summary_data).transpose().reset_index().rename(columns={"index": "Metric", 0: "Count"}).to_excel(writer, sheet_name="Summary", index=False)
        field_summary.to_excel(writer, sheet_name="Field_Summary_By_Status")
        df_res.drop(columns=["Field"], inplace=True)
        df_res.to_excel(writer, sheet_name="Audit Details", index=False)
    
    return out_buffer.getvalue(), None, []


# =========================================================
# UI
# =========================================================

def render_ui():
    st.title("ADP to Uzio Deduction Audit Tool")
    st.markdown("""
    **Instructions**:
    1. Upload **Deduction Input** File.
    2. Must contain:
        - `Uzio Data`
        - `ADP Data`
        - `Mapping Sheet`
    """)

    uploaded_file = st.file_uploader("Upload Deduction Input File", type=["xlsx"])
    client_name = st.text_input("Enter Client Name (for Report Filename)", value="Client_Name")

    if uploaded_file:
        if st.button("Run Audit", type="primary"):
            with st.spinner("Processing..."):
                try:
                    report_data, error_msg, _ = run_audit(uploaded_file.getvalue())
                    
                    if error_msg:
                        st.error(error_msg)
                    else:
                        st.success("Audit Completed Successfully!")
                        
                        client = st.session_state.get('client_name', 'Client')
                        timestamp = pd.Timestamp.now().strftime('%d_%m_%Y_%H%M')
                        filename = f"{client}_Uzio_ADP_Deduction_Audit_Report_{timestamp}.xlsx"
                        
                        st.download_button(
                            label="Download Audit Report",
                            data=report_data,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
                    st.exception(e)

if __name__ == "__main__":
    st.set_page_config(page_title="ADP Deduction Audit", layout="wide")
    render_ui()
