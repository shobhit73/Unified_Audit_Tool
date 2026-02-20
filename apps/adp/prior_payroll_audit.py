import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

# =========================================================
# ADP to Uzio Prior Payroll Audit Tool
# INPUT: One Excel File with 3 Tabs:
#   1. Uzio Data
#   2. ADP Data (Prior Payroll)
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

    return _run_prior_payroll_audit(df_uzio, df_adp, df_map)

def _run_prior_payroll_audit(df_uzio, df_adp, df_map):
    # Mapping
    map_adp_col = next((c for c in df_map.columns if "adp" in c.lower()), None)
    map_uzio_col = next((c for c in df_map.columns if "uzio" in c.lower()), None)
    
    if not map_adp_col or not map_uzio_col:
        return None, "Mapping Sheet must have columns identifying 'ADP' and 'Uzio' deductions.", []

    # Map: ADP Header -> Uzio Header
    # Normalize input mapping keys to match headers we find
    mapping = {}
    for _, row in df_map.iterrows():
        k = str(row[map_adp_col]).strip()
        v = str(row[map_uzio_col]).strip()
        
        # FIX: Allow keys even if Value is NaN (Unmapped fields that should appear in report)
        if k and k.lower() != 'nan':
            # If value is missing/nan, use the Key itself as the "mapped" name so it appears in output
            if not v or v.lower() == 'nan' or v.lower() == 'na':
                v = k
            
            mapping[k] = v
            # Also precise match for ADP columns might be needed, so keep original and normalized
            mapping[k.lower()] = v

    # --- PROCESS ADP (WIDE) ---
    adp_id_col = next((c for c in df_adp.columns if "associate" in c.lower() and "id" in c.lower()), None)
    
    # Smarter Date Column Selection for ADP
    adp_date_col = None
    adp_date_prefs = ["PAY DATE", "CHECK DATE", "PAY_DATE"]
    
    # 1. Try exact/preferred matches
    for pref in adp_date_prefs:
        match = next((c for c in df_adp.columns if pref.lower() in str(c).lower()), None)
        if match:
            adp_date_col = match
            break
            
    # 2. Fallback to generic "pay" + "date" if NOT "period"
    if not adp_date_col:
        adp_date_col = next((c for c in df_adp.columns if "pay" in c.lower() and "date" in c.lower() and "period" not in c.lower()), None)
    
    if not adp_id_col or not adp_date_col:
        return None, f"ADP Sheet missing required columns (Associate ID, Pay Date). Found: {list(df_adp.columns)}", []


    # Identify Deduction Columns in ADP Data
    # They should match keys in 'mapping'
    # We iterate ALL cols and check if they are in mapping
    
    def clean_header(h):
        # Remove common prefixes found in ADP reports
        h = str(h).strip()
        prefixes = [
            "VOLUNTARY DEDUCTION : ", 
            "ADDITIONAL HOURS : ", 
            "ADDITIONAL EARNINGS : ", 
            "DIRECT DEPOSIT : ",
            "MEMO : ",
            "MEMO - "
        ]
        for p in prefixes:
            if h.upper().startswith(p):
                return h[len(p):].strip()
        return h

    adp_deduction_map = {} # ColName -> UzioName (Mapping Value)
    
    # Pre-compute normalized mapping keys for easier lookup
    norm_mapping = {}
    for k, v in mapping.items():
        norm_mapping[str(k).strip().lower()] = v
        # Also map the cleaned version of the key itself just in case
        norm_mapping[clean_header(k).strip().lower()] = v

    for col in df_adp.columns:
        # Normalize: strip and collapse multiple spaces to single space
        norm_c = " ".join(str(col).split())
        cleaned_c = clean_header(norm_c)
        
        # 1. Try Exact Match
        if norm_c in mapping:
            adp_deduction_map[col] = mapping[norm_c]
            continue
            
        # 2. Try Case-Insensitive Match
        if norm_c.lower() in norm_mapping:
            adp_deduction_map[col] = norm_mapping[norm_c.lower()]
            continue
        
        # 3. Try Cleaned Match (e.g. "DEN-DENTAL" from "VOLUNTARY DEDUCTION : DEN-DENTAL")
        if cleaned_c in mapping:
            adp_deduction_map[col] = mapping[cleaned_c]
            continue
            
        # 4. Try Cleaned Case-Insensitive Match
        if cleaned_c.lower() in norm_mapping:
            adp_deduction_map[col] = norm_mapping[cleaned_c.lower()]
            continue

        # 5. Reverse Check: Is this ADP column actually defined as a Uzio Column Name?
        # Sometimes user puts the same name in both.
        # (Optional, but helps if mapping is sparse)

    adp_records = []
    # Melt/Unpivot
    for _, row in df_adp.iterrows():
        emp_id = str(row[adp_id_col]).strip()
        # Normalize Date
        try:
            p_date = pd.to_datetime(row[adp_date_col]).strftime("%Y-%m-%d")
        except:
            p_date = str(row[adp_date_col])
            
        for d_col, uz_name in adp_deduction_map.items():
            val = clean_money_val(row[d_col])
            if val != 0:
                adp_records.append({
                    "Employee_ID": emp_id,
                    "Pay_Date": p_date,
                    "Deduction_Name": uz_name, # Map to Common Name
                    "ADP_Raw_Code": d_col, # Use Header as code
                    "ADP_Amount": val,
                    "Key": f"{emp_id}|{p_date}|{uz_name}".lower()
                })
                
    df_adp_clean = pd.DataFrame(adp_records)
    if not df_adp_clean.empty:
         df_adp_clean = df_adp_clean.groupby(["Employee_ID", "Pay_Date", "Deduction_Name", "ADP_Raw_Code", "Key"], as_index=False)["ADP_Amount"].sum() # Sum handling duplicates
    else:
         df_adp_clean = pd.DataFrame(columns=["Employee_ID", "Pay_Date", "Deduction_Name", "ADP_Raw_Code", "Key", "ADP_Amount"])

    # --- PROCESS UZIO (WIDE) ---
    uz_id_col = next((c for c in df_uzio.columns if "employee" in c.lower() and "id" in c.lower()), None)
    
    # Smarter Date Column Selection for Uzio
    uz_date_col = None
    uz_date_prefs = ["PAY CHECK DATE", "CHECK DATE", "PAYMENT DATE"]
    
    # 1. Try exact/preferred matches
    for pref in uz_date_prefs:
        match = next((c for c in df_uzio.columns if pref.lower() in str(c).lower()), None)
        if match:
            uz_date_col = match
            break
            
    # 2. Fallback to generic "pay" + "date" if NOT "period" (ignores Period Start/End)
    if not uz_date_col:
        uz_date_col = next((c for c in df_uzio.columns if "pay" in c.lower() and "date" in c.lower() and "period" not in c.lower()), None)

    # 3. Last resort fallback (user might only have Period End Date)
    if not uz_date_col:
         uz_date_col = next((c for c in df_uzio.columns if "pay" in c.lower() and "date" in c.lower()), None)
    
    if not uz_id_col or not uz_date_col:
        return None, f"Uzio Sheet missing required columns (Employee ID, Pay Date). Found: {list(df_uzio.columns)}", []

    # Identify Deduction Columns in Uzio Data
    # We should look for columns in Uzio data that match the VALUES in the mapping dictionary
    valid_uzio_names = set(mapping.values())
    uzio_cols_found = []
    for col in df_uzio.columns:
        norm_c = str(col).strip()
        if norm_c in valid_uzio_names:
            uzio_cols_found.append(col)
            
    uzio_records = []
    for _, row in df_uzio.iterrows():
        emp_id = str(row[uz_id_col]).strip()
        try:
            p_date = pd.to_datetime(row[uz_date_col]).strftime("%Y-%m-%d")
        except:
             p_date = str(row[uz_date_col])
             
        for col in uzio_cols_found:
            val = clean_money_val(row[col])
            if val != 0:
                uzio_records.append({
                    "Uzio_Employee_ID": emp_id,
                    "Pay_Date": p_date,
                    "Uzio_Deduction_Name": col, # The header is the name
                    "Uzio_Amount": val,
                    "Key": f"{emp_id}|{p_date}|{col}".lower()
                })

    df_uz_clean = pd.DataFrame(uzio_records)
    if not df_uz_clean.empty:
        df_uz_clean = df_uz_clean.groupby(["Uzio_Employee_ID", "Pay_Date", "Uzio_Deduction_Name", "Key"], as_index=False)["Uzio_Amount"].sum()
    else:
        df_uz_clean = pd.DataFrame(columns=["Uzio_Employee_ID", "Pay_Date", "Uzio_Deduction_Name", "Key", "Uzio_Amount"])

    # --- COMPARISON ---
    merged = pd.merge(df_adp_clean, df_uz_clean, on="Key", how="outer", suffixes=('_ADP', '_UZIO'))
    
    # ID Sets for Missing Check (Needs ID + Date context?)
    uzio_all_emps = set(df_uzio[uz_id_col].astype(str).str.strip().unique())
    adp_all_emps = set(df_adp[adp_id_col].astype(str).str.strip().unique())
    
    results = []
    for _, row in merged.iterrows():
        # Recover ID and Date from available side
        if pd.notna(row.get("Employee_ID")):
            emp_id = row["Employee_ID"]
            p_date = row["Pay_Date_ADP"] if "Pay_Date_ADP" in row else row["Pay_Date"]
        else:
            emp_id = row["Uzio_Employee_ID"]
            p_date = row["Pay_Date_UZIO"] if "Pay_Date_UZIO" in row else row["Pay_Date"]

        adp_val = row["ADP_Amount"] if pd.notna(row["ADP_Amount"]) else 0.0
        uz_val = row["Uzio_Amount"] if pd.notna(row["Uzio_Amount"]) else 0.0
        
        has_adp = pd.notna(row["ADP_Amount"])
        has_uzio = pd.notna(row["Uzio_Amount"])
        
        # FIX: If Uzio value is missing, we still want to show what the ADP field *mapped to*
        if has_uzio:
            uz_name = row["Uzio_Deduction_Name"]
        elif has_adp and pd.notna(row.get("Deduction_Name")):
            # If we have ADP data, we know what it mapped to
            uz_name = row["Deduction_Name"]
        else:
            uz_name = "Not Available"
        
        # Name resolution continued
        adp_desc = row["ADP_Raw_Code"] if has_adp else "Not Available"

        # Comparison Logic with type safety
        status = ""
        is_match = False
        
        # Check if values are numeric
        is_adp_num = isinstance(adp_val, (int, float))
        is_uz_num = isinstance(uz_val, (int, float))
        
        if has_adp and has_uzio:
            if is_adp_num and is_uz_num:
                # Numeric comparison
                if abs(adp_val - uz_val) < 0.01:
                    is_match = True
            else:
                # String comparison
                if str(adp_val).strip() == str(uz_val).strip():
                    is_match = True
            
            if is_match:
                status = "Data Match"
            else:
                status = "Data Mismatch"
                
        elif has_adp and not has_uzio:
            if emp_id in uzio_all_emps:
                status = "Value missing in Uzio (ADP has value)"
            else:
                status = "Employee ID Not Found in Uzio"
        elif has_uzio and not has_adp:
            if emp_id in adp_all_emps:
                status = "Value missing in ADP (Uzio has value)"
            else:
                status = "Employee ID Not Found in ADP"

        results.append({
            "Employee ID": emp_id,
            "Pay Date": p_date,
            "ADP field": adp_desc,
            "Uzio field": uz_name,
            "ADP Amount": adp_val,
            "Uzio Amount": uz_val,
            "Status": status
        })
        
    return _generate_output(results)

def _generate_output(results):
    df_res = pd.DataFrame(results)
    
    # Consolidate Field logic for Prior Payroll
    def get_field_name(row):
        if row["Uzio field"] != "Not Available":
            return row["Uzio field"]
        return row["ADP field"] if "ADP field" in row else "Unknown"
            
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
    st.title("ADP to Uzio Prior Payroll Audit Tool")
    st.markdown("""
    **Instructions**:
    1. Upload **Prior Payroll Input** File.
    2. Must contain:
        - `Uzio Data`
        - `ADP Data` (Prior Payroll)
        - `Mapping Sheet`
    """)

    uploaded_file = st.file_uploader("Upload Prior Payroll Input File", type=["xlsx"])
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
                        
                        timestamp = pd.Timestamp.now().strftime('%d_%m_%Y_%H%M')
                        filename = f"{client_name}_Uzio_ADP_Prior_Payroll_Audit_Report_{timestamp}.xlsx"
                        
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
    st.set_page_config(page_title="ADP Prior Payroll Audit", layout="wide")
    render_ui()
