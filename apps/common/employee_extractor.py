import streamlit as st
import pandas as pd
import io
from utils.audit_utils import check_duplicate_columns

def render_employee_extractor():
    st.title("Selective Employee Extractor")
    st.markdown("""
    **Purpose**: Extract a specific subset of employees from any census file (ADP, Paycom, or Uzio) while maintaining **100% data integrity**.
    
    **Instructions**:
    1. Upload your source census file.
    2. Paste the **Employee IDs** (comma-separated) you want to extract.
    3. Preview the results and download as Excel or CSV.
    """)
    
    uploaded_file = st.file_uploader("Upload Census File", type=["xlsx", "csv", "xlsm"], key="ee_upload")
    if not uploaded_file:
        return

    # 1. READ FILE (Strict no-mutation)
    try:
        if uploaded_file.name.lower().endswith('.csv'):
            df = pd.read_csv(uploaded_file, dtype=str)
        else:
            # For Uzio/Excel, we might need to skip rows if it's Uzio
            # We'll try to detect the header automatically
            df_header = pd.read_excel(uploaded_file, nrows=10, header=None)
            header_idx = 0
            # Heuristic: Find row with most non-nulls or known keywords
            for idx, row in df_header.iterrows():
                row_str = " ".join([str(x).lower() for x in row.tolist() if pd.notna(x)])
                if any(k in row_str for k in ['associate id', 'employee_code', 'employee id*', 'legal first name']):
                    header_idx = idx
                    break
            
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file, header=header_idx, dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return

    st.success(f"File loaded: {len(df)} rows detected.")

    # 2. INPUT IDs
    st.markdown("---")
    id_input = st.text_area("Paste Employee IDs (Comma-separated)", height=150, placeholder="e.g. 1001, 1005, 09876", help="Copy and paste your list of IDs here.")
    
    if not id_input.strip():
        st.info("Please provide Employee IDs to begin extraction.")
        return

    # Parse IDs
    id_list = [i.strip() for i in id_input.split(',') if i.strip()]
    
    # 3. IDENTIFY ID COLUMN
    # Common headers: Associate ID (ADP), Employee_Code (Paycom), Employee ID* (Uzio)
    id_col = None
    all_cols = df.columns.tolist()
    
    # Precise match first
    candidates = ['Associate ID', 'Employee_Code', ' Employee ID*', 'Employee ID', 'Employee Code', 'EE ID']
    for cand in candidates:
        if cand in all_cols:
            id_col = cand
            break
            
    # Case-insensitive fuzzy match if not found
    if not id_col:
        for col in all_cols:
            c_norm = str(col).lower().strip().replace('*', '').replace(' ', '_')
            if c_norm in ['associate_id', 'employee_id', 'employee_code', 'ee_id', 'eid']:
                id_col = col
                break
                
    if not id_col:
        st.error("Could not automatically identify the 'Employee ID' column. Please ensure your file has one of the following headers: Associate ID, Employee_Code, or Employee ID*.")
        return

    st.info(f"Targeting logic focused on column: **{id_col}**")

    # 4. FILTER
    df_filtered = df[df[id_col].astype(str).str.strip().isin(id_list)].copy()

    # 5. DATA CLEANING (Paycom Exception)
    # Clear 00/00/0000 dates as per user request
    for col in df_filtered.columns:
        if df_filtered[col].astype(str).str.contains('00/00/0000', regex=False).any():
            df_filtered[col] = df_filtered[col].replace('00/00/0000', '')

    # 6. RESULTS & DOWNLOAD
    st.markdown("---")
    if df_filtered.empty:
        st.warning(f"No employees found matching the provided IDs in column '{id_col}'.")
    else:
        st.success(f"Matched **{len(df_filtered)}** out of **{len(id_list)}** requested IDs.")
        
        # UI Table Preview
        st.markdown("### Preview (Top 100 matches)")
        st.dataframe(df_filtered.head(100), use_container_width=True, hide_index=True)
        
        # Download Buttons
        col1, col2 = st.columns(2)
        
        # Excel
        buffer_xlsx = io.BytesIO()
        df_filtered.to_excel(buffer_xlsx, index=False)
        buffer_xlsx.seek(0)
        col1.download_button(
            label="📥 Download as Excel (XLSX)",
            data=buffer_xlsx.getvalue(),
            file_name=f"Extracted_Employees_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # CSV
        buffer_csv = io.StringIO()
        df_filtered.to_csv(buffer_csv, index=False)
        col2.download_button(
            label="📄 Download as CSV",
            data=buffer_csv.getvalue(),
            file_name=f"Extracted_Employees_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
