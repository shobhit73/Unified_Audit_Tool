import streamlit as st
import pandas as pd
import io
import re
from datetime import date
from audit_utils import norm_col, clean_money_val

# =========================================================
# Paycom to Uzio Deduction Audit Tool
# =========================================================

APP_TITLE = "Paycom to Uzio Deduction Audit Tool"

def norm_str(x):
    """Normalize string, handle None/NaN."""
    if pd.isna(x) or x is None:
        return ""
    return str(x).strip()

def norm_id(x):
    """Normalize Employee ID (remove leading zeros, strip)."""
    s = norm_str(x)
    return s.lstrip("0")

def read_uzio_deduction(file):
    """
    Read Uzio Deduction Export.
    Search all sheets for header row containing 'Employee Id' and 'Deduction Name'.
    """
    xls = pd.ExcelFile(file)
    
    for sheet in xls.sheet_names:
        # Read first 20 rows
        df_raw = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)
        
        header_row_idx = None
        for idx, row in df_raw.iterrows():
            row_vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
            # Strict check: Must have Employee Id AND Deduction Name
            if any("employee id" in v for v in row_vals) and any("deduction name" in v for v in row_vals):
                header_row_idx = idx
                break
        
        if header_row_idx is not None:
             # Found it!
             if hasattr(file, 'seek'):
                 file.seek(0)
             df = pd.read_excel(xls, sheet_name=sheet, header=header_row_idx)
             # Normalize columns
             df.columns = [norm_col(c) for c in df.columns]
             return df

    # Fallback if strict check fails: Try just Employee Id
    if hasattr(file, 'seek'):
         file.seek(0)
         
    for sheet in xls.sheet_names:
        df_raw = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)
        for idx, row in df_raw.iterrows():
             row_vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
             if any("employee id" in v for v in row_vals):
                  if hasattr(file, 'seek'):
                      file.seek(0)
                  df = pd.read_excel(xls, sheet_name=sheet, header=idx)
                  df.columns = [norm_col(c) for c in df.columns]
                  return df
                  
    raise ValueError("Could not find 'Employee Id' column in any sheet.")

def run_audit(file_uzio, file_paycom, file_mapping):
    # 1. Load Data
    
    # Uzio
    try:
        df_uzio = read_uzio_deduction(file_uzio)
    except Exception as e:
        return None, f"Error reading Uzio file: {e}", []

    # Paycom (CSV)
    try:
        # Scan for header row
        p_header_idx = 0
        with io.BytesIO(file_paycom.getvalue()) as f:
            # Wrap in text wrapper
            import csv
            wrapper = io.TextIOWrapper(f, encoding='utf-8', errors='replace')
            # Read first 100 lines
            for i in range(100):
                line = wrapper.readline()
                if "Code" in line and "Amount" in line:
                    p_header_idx = i
                    break
            wrapper.detach() # Detach before closing if necessary, or just let context manager handle
            
        # Re-read with found header
        # Using open_workbook or specialized reader might be better but read_csv is flexible
        # Reset pointer
        file_paycom.seek(0)
        df_paycom = pd.read_csv(file_paycom, header=p_header_idx)
        df_paycom.columns = [norm_col(c) for c in df_paycom.columns]
    except Exception as e:
        return None, f"Error reading Paycom file: {e}", []

    # Mapping
    try:
        if file_mapping.name.endswith('.csv'):
             df_map = pd.read_csv(file_mapping)
        else:
             df_map = pd.read_excel(file_mapping)
        df_map.columns = [norm_col(c) for c in df_map.columns]
    except Exception as e:
        return None, f"Error reading Mapping file: {e}", []

    # 2. Process Mapping
    # Expect columns roughly like "Paycom Code", "Uzio Name"
    map_p_col = next((c for c in df_map.columns if "paycom" in c.lower()), None)
    map_u_col = next((c for c in df_map.columns if "uzio" in c.lower()), None)
    
    if not map_p_col or not map_u_col:
         # Try simpler heuristic: Column 1 -> Paycom, Column 2 -> Uzio?
         # Or assume user followed instructions. Let's error if strictly not found for safety.
         # Actually, let's be flexible. If 2 columns, use them.
         if len(df_map.columns) >= 2:
             map_p_col = df_map.columns[1] # Assume Paycom Code
             map_u_col = df_map.columns[0] # Assume Uzio Name (or vice versa? User said "uzio coloumn and paycom colloumn")
             # Let's prompt user to be sure? No, strict auto-detect is better.
             # User said: "consisting of two coloumns uzio coloumn and paycom colloumn"
             # Let's check headers for keywords again
             pass
    
    if not map_p_col or not map_u_col:
        return None, f"Mapping Sheet must have headers identifying 'Uzio' and 'Paycom'. Found: {list(df_map.columns)}", []

    mapping = {} # Paycom Code -> Uzio Name
    for _, row in df_map.iterrows():
        p_val = norm_str(row[map_p_col])
        u_val = norm_str(row[map_u_col])
        if p_val and u_val:
            mapping[p_val.lower()] = u_val
            mapping[p_val] = u_val

    # 3. Process Paycom
    # Columns: EE Code, EE Name, Deduction Code, Deduction Desc, Amount, Percent
    p_id_col = next((c for c in df_paycom.columns if any(x in c.lower() for x in ["ee code", "employee code", "employee id"])), "EE Code")
    p_code_col = next((c for c in df_paycom.columns if "deduction code" in c.lower()), next((c for c in df_paycom.columns if "code" in c.lower() and "employee" not in c.lower() and "ee" not in c.lower()), "Code"))
    p_desc_col = next((c for c in df_paycom.columns if "deduction desc" in c.lower()), next((c for c in df_paycom.columns if "description" in c.lower()), "Description"))
    
    p_amt_col = next((c for c in df_paycom.columns if "amount" in c.lower() and "exempt" not in c.lower()), "Amount")
    p_rate_col = next((c for c in df_paycom.columns if any(x in c.lower() for x in ["percent", "rate"])), "Rate")
    
    paycom_data = []
    
    for _, row in df_paycom.iterrows():
        emp_id = norm_id(row.get(p_id_col))
        if not emp_id: continue
        
        raw_code = norm_str(row.get(p_code_col))
        raw_desc = norm_str(row.get(p_desc_col))
        
        # Map to Uzio Name
        # Try Code first, then Description
        ded_name = mapping.get(raw_code.lower())
        if not ded_name:
             ded_name = mapping.get(raw_desc.lower())
             
        if not ded_name:
             # Skip unmapped? Or keep as "Unmapped"?
             # Usually audit only checks mapped ones.
             continue
             
        amt = clean_money_val(row.get(p_amt_col))
        rate = clean_money_val(row.get(p_rate_col))
        
        # Use Rate if Amount is 0?
        # Often deductions like 401k use Rate (Percentage).
        # We'll store both, but comparison usually checks amount if non-zero, else rate?
        # Actually Uzio usually has "Employee Amount" and sometimes "Percentage".
        # Let's sum Amount.
        
        paycom_data.append({
            "ID": emp_id,
            "Deduction": ded_name,
            "Amount": amt,
            "Rate": rate,
            "Code": raw_code,
            "Key": f"{emp_id}|{ded_name}".lower()
        })
        
    df_p_clean = pd.DataFrame(paycom_data)
    if not df_p_clean.empty:
        # Sum duplicates?
        df_p_clean = df_p_clean.groupby(["ID", "Deduction", "Key"], as_index=False).agg({
            "Amount": "sum",
            "Rate": "max", # Rate usually constant
            "Code": "first"
        })
    else:
         df_p_clean = pd.DataFrame(columns=["ID", "Deduction", "Key", "Amount", "Rate", "Code"])

    # 4. Process Uzio
    # Columns expected: Employee Id, Deduction Name, Employee Amount
    u_id_col = next((c for c in df_uzio.columns if "employee id" in c.lower()), None)
    u_ded_col = next((c for c in df_uzio.columns if "deduction name" in c.lower()), None)
    u_amt_col = next((c for c in df_uzio.columns if "employee amount" in c.lower()), None)
    if not u_amt_col:
        u_amt_col = next((c for c in df_uzio.columns if "amount" in c.lower()), None)
        
    if not u_id_col or not u_ded_col:
         return None, f"Uzio file missing required columns (Employee Id, Deduction Name). Found: {list(df_uzio.columns)}", []

    uzio_data = []
    
    for _, row in df_uzio.iterrows():
        emp_id = norm_id(row.get(u_id_col))
        if not emp_id: continue
        
        ded_name = norm_str(row.get(u_ded_col))
        amt = clean_money_val(row.get(u_amt_col))
        
        uzio_data.append({
            "ID": emp_id,
            "Deduction": ded_name,
            "Amount": amt,
            "Key": f"{emp_id}|{ded_name}".lower()
        })
        
    df_u_clean = pd.DataFrame(uzio_data)
    if not df_u_clean.empty:
         df_u_clean = df_u_clean.groupby(["ID", "Deduction", "Key"], as_index=False)["Amount"].sum()
    else:
         df_u_clean = pd.DataFrame(columns=["ID", "Deduction", "Key", "Amount"])

    # 5. Merge and Compare
    merged = pd.merge(df_p_clean, df_u_clean, on="Key", how="outer", suffixes=("_P", "_U"))
    
    results = []
    
    for _, row in merged.iterrows():
        emp_id = row["ID_P"] if pd.notna(row["ID_P"]) else row["ID_U"]
        ded_name = row["Deduction_P"] if pd.notna(row["Deduction_P"]) else row["Deduction_U"]
        
        p_amt = row["Amount_P"] if pd.notna(row["Amount_P"]) else 0.0
        p_rate = row["Rate"] if pd.notna(row["Rate"]) else 0.0
        u_amt = row["Amount_U"] if pd.notna(row["Amount_U"]) else 0.0
        
        in_p = pd.notna(row["ID_P"])
        in_u = pd.notna(row["ID_U"])
        
        status = ""
        
        if in_p and in_u:
            # Compare
            # Logic: If Paycom Amount is 0, maybe check Rate vs Amount?
            # Or just compare Amounts.
            diff = abs(p_amt - u_amt)
            if diff < 0.01:
                status = "Data Match"
            else:
                # Check rate mismatch? E.g. 0.04 vs 4.0?
                # User had issue with % mismatch.
                status = "Data Mismatch"
        elif in_p and not in_u:
             status = "Value missing in Uzio (Paycom has value)"
        elif in_u and not in_p:
             status = "Value missing in Paycom (Uzio has value)"
             
        results.append({
            "Employee ID": emp_id,
            "Deduction Name": ded_name,
            "Paycom Code": row["Code"] if pd.notna(row["Code"]) else "",
            "Paycom Amount": p_amt,
            "Paycom Rate": p_rate,
            "Uzio Amount": u_amt,
            "Status": status
        })
        
    # Generate Output
    df_res = pd.DataFrame(results)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_res.to_excel(writer, sheet_name='Audit Details', index=False)
        
        # Summary
        if not df_res.empty:
             summary = df_res.groupby(["Status"]).size().reset_index(name="Count")
             summary.to_excel(writer, sheet_name='Summary', index=False)
             
    return output.getvalue(), None, results

def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    **Instructions**:
    1. Upload **Uzio Deduction Export** (Excel).
    2. Upload **Paycom Deduction Export** (CSV).
    3. Upload **Mapping File** (Excel/CSV with `Paycom Code` and `Uzio Name` columns).
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        u_file = st.file_uploader("Uzio Deduction File", type=["xlsx", "xls"], key="pd_u")
    with col2:
        p_file = st.file_uploader("Paycom Deduction File", type=["csv", "xlsx"], key="pd_p")
        
    m_file = st.file_uploader("Mapping Sheet", type=["xlsx", "csv"], key="pd_m")
    
    if st.button("Run Audit", type="primary"):
        if not u_file or not p_file or not m_file:
            st.error("Please upload all 3 files.")
            return
            
        with st.spinner("Processing..."):
            report, err, _ = run_audit(u_file, p_file, m_file)
            
            if err:
                st.error(err)
            else:
                st.success("Audit Complete!")
                st.download_button(
                    "Download Report",
                    data=report,
                    file_name=f"Paycom_Deduction_Audit_{date.today()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
