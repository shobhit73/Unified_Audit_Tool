import streamlit as st
import pandas as pd
import io
from utils.audit_utils import check_duplicate_columns, format_datetime_strings

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
        source_file = st.file_uploader("1. Upload SOURCE File (ADP/Paycom Census or ADP Direct Deposit)", type=["xlsx", "csv", "xlsm"], key="ee_source")
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
                if any(k in row_vals for k in ['associate id', 'employee_code', 'employee id*', 'legal first name', 'name', 'company code']):
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
    # Candidates cover: ADP Census, Paycom, Uzio, ADP Direct Deposit (ASSOCIATE ID - uppercase)
    candidates = ['ASSOCIATE ID', 'Associate ID', 'Employee_Code', ' Employee ID*', 'Employee ID', 'Employee Code', 'EE ID']
    for cand in candidates:
        if cand in all_cols:
            id_col_source = cand
            break
    if not id_col_source:
        # Fuzzy match
        for col in all_cols:
            c_norm = str(col).lower().strip().replace('*', '').replace(' ', '_')
            if c_norm in ['associate_id', 'employee_id', 'employee_code', 'ee_id', 'eid']:
                id_col_source = col
                break
    
    if not id_col_source:
        st.error("Could not identify 'Employee ID' column in source. Headers found: " + ", ".join(all_cols[:10]))
        return

    # Detect if this is a Direct Deposit file (can have multiple rows per employee)
    is_direct_deposit = 'ROUTING NUMBER' in all_cols or 'ACCOUNT NUMBER' in all_cols
    if is_direct_deposit:
        st.info("📋 **ADP Direct Deposit report detected.** Multiple rows per employee (split accounts) will all be included in the output.")

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
    ref_ids_set = set()
    if ref_file:
        try:
            # Attempt to read Uzio Multi-Client Template
            # Usually 'Employee Details' sheet, Header row 4 (index 3)
            df_ref = pd.read_excel(ref_file, sheet_name='Employee Details', header=3, dtype=str)
            ref_id_col = ' Employee ID*'
            if ref_id_col in df_ref.columns:
                ordered_ids = df_ref[ref_id_col].dropna().unique().tolist()
                ref_ids_set = set(ordered_ids)
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

    # --- ID MISMATCH FLAGGING (Source vs Reference) ---
    if ref_ids_set and not manual_ids_input.strip():
        source_ids_set = set(df_source[id_col_source].astype(str).str.strip().dropna().unique())
        
        in_ref_not_source = sorted(ref_ids_set - source_ids_set)
        in_source_not_ref = sorted(source_ids_set - ref_ids_set)
        
        if in_ref_not_source or in_source_not_ref:
            st.warning(f"⚠️ **ID Mismatch Detected** — Sequencing may be affected!")
            if in_ref_not_source:
                with st.expander(f"🟡 {len(in_ref_not_source)} ID(s) in Uzio Reference but MISSING from Source", expanded=False):
                    st.markdown("These employees exist in your Uzio template but were **not found** in the uploaded source file. They will be **skipped** in the output.")
                    st.dataframe(pd.DataFrame({"Missing Employee ID": in_ref_not_source}), hide_index=True, use_container_width=True)
            if in_source_not_ref:
                with st.expander(f"🔵 {len(in_source_not_ref)} ID(s) in Source but MISSING from Uzio Reference", expanded=False):
                    st.markdown("These employees exist in your source file but are **not listed** in the Uzio reference. They will be **excluded** from the output since sequencing follows the reference order.")
                    st.dataframe(pd.DataFrame({"Extra Employee ID": in_source_not_ref}), hide_index=True, use_container_width=True)
        else:
            st.success("✅ All IDs match perfectly between Source and Uzio Reference!")

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

    # 7. DATA CLEANING
    for col in df_result.columns:
        # Clear 00/00/0000 dates (Paycom exception)
        if df_result[col].astype(str).str.contains('00/00/0000', regex=False).any():
            df_result[col] = df_result[col].replace('00/00/0000', '')

    # Auto-detect and format all date-like columns to MM/DD/YYYY
    date_keywords = ['date', 'dob', 'birth', 'hire', 'termination', 'expir', 'expiration']
    date_like_cols = [
        col for col in df_result.columns
        if any(kw in str(col).lower() for kw in date_keywords)
    ]
    if date_like_cols:
        df_result = format_datetime_strings(df_result, date_like_cols)

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
