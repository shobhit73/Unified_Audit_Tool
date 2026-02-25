import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime, date
import numpy as np

APP_TITLE = "ADP License Details Audit"

# --- HELPER FUNCTIONS ---
def norm_blank(x):
    """Normalize NaN, None, or completely whitespace strings to empty string."""
    if pd.isna(x) or x is None:
        return ""
    if isinstance(x, str):
        s = x.strip()
        if not s:
             return ""
        return s
    return x

def try_parse_date(x):
    """Safely parse a date string or object into YYYY-MM-DD string."""
    x = norm_blank(x)
    if x == "":
        return ""
    if isinstance(x, (datetime, date, np.datetime64, pd.Timestamp)):
        return pd.to_datetime(x).strftime('%Y-%m-%d')
    if isinstance(x, str):
        # Handle '1900-01-01 00:00:00' common Excel raw string formats
        s = x.strip().split(' ')[0]
        try:
            return pd.to_datetime(s, errors="raise").strftime('%Y-%m-%d')
        except Exception:
            return s
    return str(x)

def read_uzio_license(file) -> pd.DataFrame:
    """Reads UZIO license report, extracting exact headers while bypassing corrupt metadata."""
    try:
        df = pd.read_excel(file, dtype=str)
        return df
    except Exception:
        # Fallback to Openpyxl for corrupt metadata
        import openpyxl
        import warnings
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            wb = openpyxl.load_workbook(file, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            
            # Find the header row by looking for 'Employee ID'
            header_idx = -1
            for i, r in enumerate(rows[:20]):
                if any(str(c).strip() == 'Employee ID' for c in r if c):
                    header_idx = i
                    break
            
            if header_idx == -1:
                st.error("Could not locate 'Employee ID' header in Uzio file.")
                return None
                
            cols = [str(c).strip() if c else f"Unnamed_{i}" for i, c in enumerate(rows[header_idx])]
            data = rows[header_idx + 1:]
            df = pd.DataFrame(data, columns=cols).astype(str)
            # Remove entirely empty rows
            df = df.replace('None', '')
            df.dropna(how='all', inplace=True)
            return df

def read_adp_license(file) -> pd.DataFrame:
    """Reads ADP license report, extracting headers while bypassing metadata."""
    try:
         df = pd.read_excel(file, dtype=str)
         return df
    except Exception:
         import openpyxl
         import warnings
         with warnings.catch_warnings(record=True):
             warnings.simplefilter("always")
             wb = openpyxl.load_workbook(file, data_only=True)
             ws = wb.active
             rows = list(ws.iter_rows(values_only=True))
             
             # Locate header row
             header_idx = -1
             for i, r in enumerate(rows[:20]):
                 if any(str(c).strip() == 'Associate ID' for c in r if c):
                     header_idx = i
                     break
                     
             if header_idx == -1:
                 st.error("Could not locate 'Associate ID' header in ADP file.")
                 return None
                 
             cols = [str(c).strip() if c else f"Unnamed_{i}" for i, c in enumerate(rows[header_idx])]
             data = rows[header_idx + 1:]
             df = pd.DataFrame(data, columns=cols).astype(str)
             df = df.replace('None', '')
             df.dropna(how='all', inplace=True)
             return df

# --- AUDIT LOGIC ---
def run_license_audit(uzio_df, adp_df):
    """
    Compares Uzio and ADP License data based on:
      Uzio: Employee ID, License Type, License Number, License Expiration Date
      ADP: Associate ID, License/Certification Description, License/Certification ID, Expiration Date
    """
    
    UZIO_KEY = 'Employee ID'
    ADP_KEY = 'Associate ID'
    
    UZIO_TYPE_COL = 'License Type'
    UZIO_NUM_COL = 'License Number'
    UZIO_DATE_COL = 'License Expiration Date'
    
    ADP_TYPE_COL = 'License/Certification Description'
    ADP_NUM_COL = 'License/Certification ID'
    ADP_DATE_COL = 'Expiration Date'
    
    required_uzio = [UZIO_KEY, UZIO_TYPE_COL, UZIO_NUM_COL, UZIO_DATE_COL]
    required_adp = [ADP_KEY, ADP_TYPE_COL, ADP_NUM_COL, ADP_DATE_COL]
    
    for c in required_uzio:
        if c not in uzio_df.columns:
            st.error(f"Missing required Uzio column: {c}")
            return None
            
    for c in required_adp:
        if c not in adp_df.columns:
            st.error(f"Missing required ADP column: {c}")
            return None
            
    # Normalize Keys
    uzio_df[UZIO_KEY] = uzio_df[UZIO_KEY].apply(lambda x: str(x).strip().lstrip('0') if norm_blank(x) != "" else "")
    adp_df[ADP_KEY] = adp_df[ADP_KEY].apply(lambda x: str(x).strip().lstrip('0') if norm_blank(x) != "" else "")
    
    all_keys = sorted(list(set(uzio_df[UZIO_KEY].unique()).union(set(adp_df[ADP_KEY].unique()))))
    all_keys = [k for k in all_keys if k]
    
    # Pre-process DataFrames into dictionaries of records for faster lookup
    uzio_records = uzio_df.to_dict('records')
    adp_records = adp_df.to_dict('records')
    
    uzio_map = {}
    for r in uzio_records:
        k = r[UZIO_KEY]
        if k:
            if k not in uzio_map:
                uzio_map[k] = []
            uzio_map[k].append(r)
            
    adp_map = {}
    for r in adp_records:
        k = r[ADP_KEY]
        if k:
            if k not in adp_map:
                adp_map[k] = []
            adp_map[k].append(r)
            
    rows = []
    
    # Process each employee ID uniquely
    for eid in all_keys:
        uzio_licenses = uzio_map.get(eid, [])
        adp_licenses = adp_map.get(eid, [])
        
        # Scenario 1: Missing in Uzio
        if not uzio_licenses and adp_licenses:
            for adp_rec in adp_licenses:
                 adp_type = str(adp_rec.get(ADP_TYPE_COL, "")).strip()
                 
                 rows.append({
                     "Employee ID": eid,
                     "Audit Field": f"License Type",
                     "Expected Uzio License": adp_type,
                     "Uzio License Found": "",
                     "ADP License Name": adp_type,
                     "Uzio Value": "",
                     "ADP Value": adp_type,
                     "Audit Status": "Employee ID not in Uzio (present in adp)" if not uzio_licenses and not any(r[UZIO_KEY] == eid for r in uzio_records) else "Missing in Uzio"
                 })
                 
        # Scenario 2: Missing in ADP
        elif uzio_licenses and not adp_licenses:
            for uz_rec in uzio_licenses:
                 uz_type = str(uz_rec.get(UZIO_TYPE_COL, "")).strip()
                 
                 rows.append({
                     "Employee ID": eid,
                     "Audit Field": f"License Type",
                     "Expected Uzio License": uz_type,
                     "Uzio License Found": uz_type,
                     "ADP License Name": "",
                     "Uzio Value": uz_type,
                     "ADP Value": "",
                     "Audit Status": "Employee ID not in ADP (Present in uzio)" if not adp_licenses and not any(r[ADP_KEY] == eid for r in adp_records) else "Missing in ADP"
                 })
                 
        # Scenario 3: Exists in both, compare line items
        elif uzio_licenses and adp_licenses:
            
            # Keep track of matched ADP licenses
            matched_adp_indices = set()
            
            # Iterate through Uzio licenses
            for uz_rec in uzio_licenses:
                uz_type = str(uz_rec.get(UZIO_TYPE_COL, "")).strip()
                uz_num = str(uz_rec.get(UZIO_NUM_COL, "")).strip()
                uz_raw_date = uz_rec.get(UZIO_DATE_COL, "")
                uz_date = try_parse_date(uz_raw_date)
                
                # Find matching ADP license
                match_found = False
                for i, adp_rec in enumerate(adp_licenses):
                    if i in matched_adp_indices:
                        continue
                        
                    adp_type = str(adp_rec.get(ADP_TYPE_COL, "")).strip()
                    
                    # Direct check without mapping dictionary
                    if uz_type.lower() == adp_type.lower() and adp_type != "":
                        match_found = True
                        matched_adp_indices.add(i)
                        
                        adp_num = str(adp_rec.get(ADP_NUM_COL, "")).strip()
                        adp_raw_date = adp_rec.get(ADP_DATE_COL, "")
                        adp_date = try_parse_date(adp_raw_date)
                        
                        # Compare Number
                        if uz_num != adp_num:
                            rows.append({
                                 "Employee ID": eid,
                                 "Audit Field": "License Number",
                                 "Expected Uzio License": uz_type,
                                 "Uzio License Found": uz_type,
                                 "ADP License Name": adp_type,
                                 "Uzio Value": uz_num,
                                 "ADP Value": adp_num,
                                 "Audit Status": "Data Mismatch"
                             })
                        else:
                             rows.append({
                                 "Employee ID": eid,
                                 "Audit Field": "License Number",
                                 "Expected Uzio License": uz_type,
                                 "Uzio License Found": uz_type,
                                 "ADP License Name": adp_type,
                                 "Uzio Value": uz_num,
                                 "ADP Value": adp_num,
                                 "Audit Status": "Data Match"
                             })
                             
                        # Compare Expiration Date
                        if uz_date != adp_date:
                            rows.append({
                                 "Employee ID": eid,
                                 "Audit Field": "Expiration Date",
                                 "Expected Uzio License": uz_type,
                                 "Uzio License Found": uz_type,
                                 "ADP License Name": adp_type,
                                 "Uzio Value": uz_date,
                                 "ADP Value": adp_date,
                                 "Audit Status": "Data Mismatch"
                             })
                        else:
                            rows.append({
                                 "Employee ID": eid,
                                 "Audit Field": "Expiration Date",
                                 "Expected Uzio License": uz_type,
                                 "Uzio License Found": uz_type,
                                 "ADP License Name": adp_type,
                                 "Uzio Value": uz_date,
                                 "ADP Value": adp_date,
                                 "Audit Status": "Data Match"
                             })
                             
                        break # Stop looking for this Uzio license type
                        
                # If no ADP match was found for this Uzio license
                if not match_found:
                    rows.append({
                         "Employee ID": eid,
                         "Audit Field": "License Type",
                         "Expected Uzio License": uz_type,
                         "Uzio License Found": uz_type,
                         "ADP License Name": "",
                         "Uzio Value": uz_type,
                         "ADP Value": "",
                         "Audit Status": "Missing in ADP"
                     })
                     
            # For any ADP licenses that were NOT matched to Uzio
            for i, adp_rec in enumerate(adp_licenses):
                if i not in matched_adp_indices:
                     adp_type = str(adp_rec.get(ADP_TYPE_COL, "")).strip()
                     
                     rows.append({
                         "Employee ID": eid,
                         "Audit Field": "License Type",
                         "Expected Uzio License": adp_type,
                         "Uzio License Found": "",
                         "ADP License Name": adp_type,
                         "Uzio Value": "",
                         "ADP Value": adp_type,
                         "Audit Status": "Missing in Uzio"
                     })

    return pd.DataFrame(rows)

# --- UI RENDER FLOW ---
def render_ui():
    st.title("ADP License Details Audit Tool")
    st.write("Compare license numbers, types, and expiration dates between ADP and Uzio.")

    # Track Client Name uniquely
    client_name = st.text_input("Client Name", key="adp_license_client_name")

    st.markdown("### Step 1: Upload Files")
    col1, col2 = st.columns(2)
    with col1:
        uzio_file = st.file_uploader("Upload UZIO License Report (.xlsx)", type=['xlsx', 'csv'], key='uzio_license_upload')
    with col2:
        adp_file = st.file_uploader("Upload ADP License Report (.xlsx)", type=['xlsx', 'csv'], key='adp_license_upload')

    if uzio_file and adp_file:
        try:
            with st.spinner("Extracting Unique Licenses..."):
                uzio_df = read_uzio_license(uzio_file)
                adp_df = read_adp_license(adp_file)

            if uzio_df is None or adp_df is None:
                st.error("Failed to parse one or both files.")
                return

            uzio_types = sorted(list(set(str(t).strip() for t in uzio_df['License Type'].dropna() if t)))
            adp_types = sorted(list(set(str(t).strip() for t in adp_df['License/Certification Description'].dropna() if t)))

            st.success(f"Files loaded successfully. Found {len(adp_types)} unique ADP License Types and {len(uzio_types)} unique Uzio License Types.")

            submit_audit = st.button("Run License Audit")

            if submit_audit:
                 if not client_name:
                     st.warning("Please enter a Client Name before running the audit.")
                     return

                 with st.spinner("Running Audit & Generating Match Report..."):
                     result_df = run_license_audit(uzio_df, adp_df)
                     
                 if result_df is not None:
                      st.success("Audit Complete!")
                      
                      # Create summary counts
                      st.markdown("### Audit Summary")
                      
                      col1, col2, col3, col4 = st.columns(4)
                      counts = result_df['Audit Status'].value_counts().to_dict()
                      
                      col1.metric("Total Match", counts.get("Data Match", 0))
                      col2.metric("Total Mismatch", counts.get("Data Mismatch", 0))
                      col3.metric("Missing in UZIO", counts.get("Missing in Uzio", 0) + counts.get("Employee ID not in Uzio (present in adp)", 0))
                      col4.metric("Missing in ADP", counts.get("Missing in ADP", 0) + counts.get("Employee ID not in ADP (Present in uzio)", 0))

                      st.dataframe(result_df)

                      # Download Button
                      output_filename = f"{client_name.strip()}_License_Audit_Report_{datetime.now().strftime('%d_%m_%Y')}.xlsx"
                      
                      buffer = io.BytesIO()
                      with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                          result_df.to_excel(writer, sheet_name='License Audit Results', index=False)

                      st.download_button(
                          label="Download Excel Report",
                          data=buffer.getvalue(),
                          file_name=output_filename,
                          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                      )
                      
        except Exception as e:
            st.error(f"Error processing files: {e}")
