import streamlit as st
import pandas as pd
import io
from utils.audit_utils import check_duplicate_columns

def render_employee_extractor():
    st.title("Selective Employee Extractor (Selective Sync & Sequence)")
    st.markdown("""
    **Purpose**: Extract a specific subset of employees from any census file while maintaining **100% data integrity** and **controlling the sequence**.
    
    **Features**:
    - **Sequencing**: Re-order rows to match an Uzio Census or a custom list.
    - **Column Selection**: Pick only the fields you need (e.g., ID + License Expiry).
    - **Zero Tampering**: Preserves original formats/leading zeros.
    """)
    
    # 1. FILE UPLOADERS
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        source_file = st.file_uploader("1. Upload SOURCE Census (ADP/Paycom)", type=["xlsx", "csv", "xlsm"], key="ee_source")
    with col_u2:
        ref_file = st.file_uploader("2. Upload REFERENCE Order (Uzio Census) - OPTIONAL", type=["xlsx", "xlsm"], key="ee_ref")

    if not source_file:
        st.info("Please upload a source file to begin.")
        return

    # 2. READ SOURCE (Strict no-mutation)
    try:
        source_file.seek(0)
        if source_file.name.lower().endswith('.csv'):
            df_source = pd.read_csv(source_file, dtype=str)
        else:
            # Automatic header detection for Source
            df_header = pd.read_excel(source_file, nrows=10, header=None)
            header_idx = 0
            for idx, row in df_header.iterrows():
                row_vals = [str(x).lower().strip() for x in row.tolist() if pd.notna(x)]
                if any(k in row_vals for k in ['associate id', 'employee_code', 'employee id*', 'legal first name']):
                    header_idx = idx
                    break
            source_file.seek(0)
            df_source = pd.read_excel(source_file, header=header_idx, dtype=str)
    except Exception as e:
        st.error(f"Error reading source file: {e}")
        return

    st.success(f"Source file loaded: {len(df_source)} rows, {len(df_source.columns)} columns.")

    # 3. IDENTIFY ID COLUMN (Source)
    id_col_source = None
    all_cols = df_source.columns.tolist()
    candidates = ['Associate ID', 'Employee_Code', ' Employee ID*', 'Employee ID', 'Employee Code', 'EE ID']
    for cand in candidates:
        if cand in all_cols:
            id_col_source = cand
            break
    if not id_col_source:
        # Fuzzy
        for col in all_cols:
            c_norm = str(col).lower().strip().replace('*', '').replace(' ', '_')
            if c_norm in ['associate_id', 'employee_id', 'employee_code', 'ee_id', 'eid']:
                id_col_source = col
                break
    
    if not id_col_source:
        st.error("Could not identify 'Employee ID' column in source. Headers found: " + ", ".join(all_cols[:10]))
        return

    # 4. COLUMN SELECTOR
    st.markdown("---")
    st.markdown("### 2. Choose Columns to Include")
    include_all = st.checkbox("Include ALL columns", value=False)
    selected_cols = []
    if include_all:
        selected_cols = all_cols
    else:
        selected_cols = st.multiselect("Select columns from source", all_cols, default=[id_col_source] if id_col_source in all_cols else [])

    if not selected_cols:
        st.warning("Please select at least one column.")
        return

    # 5. DEFINE SEQUENCE
    st.markdown("---")
    st.markdown("### 3. Define Employee Sequence")
    
    ordered_ids = []
    if ref_file:
        try:
            # Attempt to read Uzio Multi-Client Template
            # Usually 'Employee Details' sheet, Header row 4 (index 3)
            df_ref = pd.read_excel(ref_file, sheet_name='Employee Details', header=3, dtype=str)
            ref_id_col = ' Employee ID*'
            if ref_id_col in df_ref.columns:
                ordered_ids = df_ref[ref_id_col].dropna().unique().tolist()
                st.info(f"Loaded **{len(ordered_ids)}** IDs from Uzio Reference (Order strictly matched).")
            else:
                st.error("Reference file uploaded but ' Employee ID*' column not found in 'Employee Details' sheet.")
        except Exception as e:
            st.error(f"Error reading Reference file: {e}. Ensure it is a valid Uzio Census Template.")
    
    # Manual Input (Fallback or Hybrid)
    manual_ids_input = st.text_area("Paste Employee IDs (Comma-separated) - Use this if no reference file or to override", 
                                   height=100, 
                                   help="IDs provided here will be used in exactly this order.")
    if manual_ids_input.strip():
        manual_ids = [i.strip() for i in manual_ids_input.split(',') if i.strip()]
        if ordered_ids:
            st.warning("Both Reference File and Manual IDs provided. **Using Manual List** for final sequence.")
        ordered_ids = manual_ids

    if not ordered_ids:
        st.info("Waiting for Reference File or Manual ID list to define the sequence...")
        return

    # 6. EXTRACTION LOGIC
    # Re-indexing is the best way to maintain exact sequence
    # Note: We must handle IDs present in Uzio but missing in Source (they will result in blank rows)
    # The user said "carve out those employee rows", implying we keep those found.
    
    df_source[id_col_source] = df_source[id_col_source].astype(str).str.strip()
    
    # We filter first to existing rows to avoid creating empty "NaN" rows 
    # unless specified (but usually users want existing data only)
    existing_ids = set(df_source[id_col_source].tolist())
    final_id_list = [i for i in ordered_ids if i in existing_ids]

    # Map target ID to its position in the requested sequence
    id_to_pos = {id_val: i for i, id_val in enumerate(ordered_ids)}
    
    # Filter and Sort
    df_result = df_source[df_source[id_col_source].isin(final_id_list)].copy()
    df_result['sort_key'] = df_result[id_col_source].map(id_to_pos)
    df_result = df_result.sort_values('sort_key').drop(columns=['sort_key'])
    
    # Final column subset
    df_result = df_result[selected_cols]

    # 7. DATA CLEANING (Paycom Exception + Timestamp cleanup)
    for col in df_result.columns:
        # Clear 00/00/0000 dates
        if df_result[col].astype(str).str.contains('00/00/0000', regex=False).any():
            df_result[col] = df_result[col].replace('00/00/0000', '')
        
        # Cleanup trailing 00:00:00 from pandas read_excel(dtype=str)
        if df_result[col].astype(str).str.endswith(' 00:00:00').any():
            df_result[col] = df_result[col].astype(str).str.replace(' 00:00:00', '', regex=False).replace('nan', '')

    # 8. RESULTS & DOWNLOAD
    st.markdown("---")
    if df_result.empty:
        st.warning("No employees found matching the sequence criteria.")
    else:
        st.success(f"Matched **{len(df_result)}** employees in the specified sequence.")
        st.dataframe(df_result.head(100), use_container_width=True, hide_index=True)
        
        col1, col2 = st.columns(2)
        # Excel
        buffer_xlsx = io.BytesIO()
        df_result.to_excel(buffer_xlsx, index=False)
        buffer_xlsx.seek(0)
        col1.download_button("📥 Download Excel", buffer_xlsx.getvalue(), f"Selective_Census_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        # CSV
        buffer_csv = io.StringIO()
        df_result.to_csv(buffer_csv, index=False)
        col2.download_button("📄 Download CSV", buffer_csv.getvalue(), f"Selective_Census_{pd.Timestamp.now().strftime('%Y%m%d')}.csv", "text/csv")
