import io
import pandas as pd
import streamlit as st
from utils.audit_utils import generate_uzio_template, check_duplicate_columns, format_datetime_strings

APP_TITLE = "ADP to Uzio Census Template Generator"

ADP_FIELD_MAP = {
    'Employee ID': ['Associate ID'],
    'First Name': ['Legal First Name'],
    'Last Name': ['Legal Last Name'],
    'Middle Initial': ['Legal Middle Name'],
    'Suffix': ['Generation Suffix Code'],
    'Employment Status': ['Position Status'],
    'Employment Type': ['Worker Category Description'],
    'Hire Date': ['Hire/Rehire Date'],
    'Original Hire Date': ['Hire Date'],
    'Termination Date': ['Termination Date'],
    'Termination Reason': ['Termination Reason Description'],
    'Pay Type': ['Regular Pay Rate Description'],
    'Annual Salary': ['Annual Salary'],
    'Hourly Pay Rate': ['Regular Pay Rate Amount'],
    'Working Hours': ['Standard Hours'],
    'Job Title': ['Job Title Description'],
    'Department': ['Department Description'],
    'Work Email': ['Work Contact: Work Email'],
    'Personal Email': ['Personal Contact: Personal Email'],
    'SSN': ['Tax ID (SSN)'],
    'DOB': ['Birth Date'],
    'Gender': ['Gender / Sex (Self-ID)'],
    'Tobacco User': ['Tobacco User'],
    'FLSA Classification': ['FLSA Description'],
    'Address Line 1': ['Primary Address: Address Line 1'],
    'Address Line 2': ['Primary Address: Address Line 2'],
    'City': ['Primary Address: City'],
    'Zip': ['Primary Address: Zip / Postal Code'],
    'State': ['Primary Address: State / Territory Code'],
    'Mailing Address Line 1': ['Legal / Preferred Address: Address Line 1'],
    'Mailing Address Line 2': ['Legal / Preferred Address: Address Line 2'],
    'Mailing City': ['Legal / Preferred Address: City'],
    'Mailing Zip': ['Legal / Preferred Address: Zip / Postal Code'],
    'Mailing State': ['Legal / Preferred Address: State / Territory Code'],
    'Reports To ID': ['Reports To Associate ID'],
    'Work Location': ['Location Description']
}

ALLOWED_JOB_TITLES = [
    'DSP Owner', 'Operations Manager', 'Operations Lead', 'Fleet Manager', 
    'Safety Manager', 'Performance Manager', 'Trainer', 'Human Resources', 
    'Recruiter', 'Office Personnel', 'Payroll Assistant', 'Finance', 
    'Dispatch', 'Management', 'Admin', 'Survey', 'Warehouse', 'Walker', 
    'Driver', 'Helper', 'Driver-Lite', 'Driver-Step Van', 
    'Driver-Unscheduled', 'Lead Driver', 'DDU Dedicated', 'DDU Shared', 
    'Non-DSP Related', 'Driver -Major Appliance'
]

def norm_colname(c: str) -> str:
    import re
    if c is None: return ""
    c = str(c).replace("\n", " ").replace("\r", " ")
    c = c.replace("\u00A0", " ")
    c = re.sub(r'\(.*?\)', '', c)
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "")
    c = c.strip('"').strip("'")
    return c.lower()

def preprocess_adp_file(adp_file):
    """Common logic for reading and normalizing ADP file."""
    # --- CRITICAL ERROR: Duplicate Column Check ---
    dupes = check_duplicate_columns(adp_file)
    if dupes:
        st.error(f"⛔ **Critical Error: Duplicate Column Headers Found!**")
        st.markdown(f"The following column headers appear multiple times in your file: **{', '.join(dupes)}**")
        st.warning("Pandas cannot process files with duplicate headers accurately. Please delete the duplicate columns and re-upload the file.")
        return None, None, None, None

    try:
        if adp_file.name.lower().endswith('.csv'):
            try:
                df_adp = pd.read_csv(adp_file, dtype=str)
            except UnicodeDecodeError:
                adp_file.seek(0)
                df_adp = pd.read_csv(adp_file, dtype=str, encoding='latin1')
        else:
            df_adp = pd.read_excel(adp_file, dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None, None, None, None

    # Save original column headers before normalization
    original_columns = list(df_adp.columns)
    
    # Normalize source columns
    df_adp.columns = [norm_colname(c) for c in df_adp.columns]
    
    # Build mapping: normalized -> original (for restoring headers on download)
    norm_to_orig = dict(zip(df_adp.columns, original_columns))
    
    # Resolve field map
    resolved_field_map = {}
    for std_name, vendor_cols in ADP_FIELD_MAP.items():
        found = False
        for vc in vendor_cols:
            norm_vc = norm_colname(vc)
            if norm_vc in df_adp.columns:
                resolved_field_map[std_name] = norm_vc
                found = True
                break
        if not found:
            resolved_field_map[std_name] = norm_colname(vendor_cols[0])
            
    return df_adp, original_columns, norm_to_orig, resolved_field_map

def render_auto_fix_options(key_prefix):
    """Shared auto-correction options UI."""
    st.markdown("### 🛠️ **Auto-Correction Options (Manual Consent Required)**")
    st.markdown("Select which automated fixes you would like to apply.")
    
    col_fix1, col_fix2 = st.columns(2)
    with col_fix1:
        fix_flsa = st.checkbox("Enforce FLSA/Pay Type alignment (e.g. Salaried = Exempt)", value=False, key=f"{key_prefix}_fix_flsa")
        fix_emails = st.checkbox("Use Personal Email as fallback for missing Work Email", value=False, key=f"{key_prefix}_fix_emails")
        fix_job_title = st.checkbox("Auto-Fill blank Job Titles using Department Description", value=False, key=f"{key_prefix}_fix_jt")
        fix_license = st.checkbox("Strict License Validation (Clear dates if number missing)", value=False, key=f"{key_prefix}_fix_license")
    with col_fix2:
        fix_status = st.checkbox("Auto-Map Employment Status (e.g. Inactive -> Terminated)", value=False, key=f"{key_prefix}_fix_status")
        fix_type = st.checkbox("Auto-Map Worker Category (e.g. Intern -> Part Time)", value=False, key=f"{key_prefix}_fix_type")
        fix_dol_status = st.checkbox("Auto-Fill blank DOL_Status to 'Full-Time' for Active Employees", value=True, key=f"{key_prefix}_fix_dol_status")

    return {
        'fix_flsa': fix_flsa,
        'fix_emails': fix_emails,
        'fix_job_title': fix_job_title,
        'fix_license': fix_license,
        'fix_status': fix_status,
        'fix_inactive': fix_status,
        'fix_type': fix_type,
        'fix_dol_status': fix_dol_status
    }

def get_manager_info(df_adp, resolved_field_map):
    """Detection logic for top manager (ADP uses 'Reports To Associate ID')."""
    col_sup_code = resolved_field_map.get('Reports To ID')
    if not col_sup_code or col_sup_code not in df_adp.columns:
        if 'reports to associate id' in df_adp.columns:
            col_sup_code = 'reports to associate id'

    top_manager_id = None
    top_manager_name = ""
    has_managers = False

    if col_sup_code and col_sup_code in df_adp.columns:
        valid_sups = df_adp[df_adp[col_sup_code].notna() & (df_adp[col_sup_code].astype(str).str.strip() != "")]
        if not valid_sups.empty:
            has_managers = True
            sup_counts = valid_sups[col_sup_code].value_counts()
            if not sup_counts.empty:
                top_manager_id = str(sup_counts.index[0]).strip()
                emp_code_col = resolved_field_map.get('Employee ID')
                if emp_code_col and emp_code_col in df_adp.columns:
                    match = df_adp[df_adp[emp_code_col].astype(str).str.strip() == top_manager_id]
                    if not match.empty:
                        fn = match.iloc[0].get(resolved_field_map.get('First Name'), '')
                        ln = match.iloc[0].get(resolved_field_map.get('Last Name'), '')
                        if pd.notna(fn) and pd.notna(ln):
                            top_manager_name = f"{str(fn).strip()} {str(ln).strip()}".strip()
    return has_managers, top_manager_id, top_manager_name, col_sup_code

def render_census_sanity_check():
    st.title("ADP Census Sanity Check")
    st.markdown("""
    **Instructions**:
    1. Upload your **ADP Census Export**.
    2. Review the detected errors and mapping suggestions.
    3. Download the **Corrected Source Data** containing automated fixes.
    """)
    
    adp_file = st.file_uploader("Upload ADP Census Export", type=["xlsx", "csv"], key="adp_sanity_upload")
    if not adp_file: return

    df_adp, original_columns, norm_to_orig, resolved_field_map = preprocess_adp_file(adp_file)
    if df_adp is None: return

    has_managers, top_manager_id, top_manager_name, col_sup_code = get_manager_info(df_adp, resolved_field_map)
    sort_by_manager = False
    if has_managers and top_manager_id:
        name_disp = f" ({top_manager_name})" if top_manager_name else ""
        st.info(f"**Top Manager Detected:** Employee **{top_manager_id}**{name_disp}")
        sort_by_manager = st.checkbox("Sort all reporting managers to the top of download file", value=True, key="adp_sanity_sort_mgr")
    fix_options = render_auto_fix_options("adp_sanity")
    
    # --- MAPPING UI ---
    st.markdown("### 🗺️ Mapping Configuration (Optional)")
    st.info("Provide mappings here to include them in the **Corrected Source** download.")
    
    src_loc_col = resolved_field_map.get('Work Location')
    unique_locs = sorted([str(l).strip() for l in df_adp[src_loc_col].dropna().unique()]) if src_loc_col and src_loc_col in df_adp.columns else []

    st.write("**Work Location Mapping**")
    edited_locs = st.data_editor(
        pd.DataFrame({"Source Work Location": unique_locs, "Mapped Uzio Work Location": [""]*len(unique_locs)}),
        column_config={"Mapped Uzio Work Location": st.column_config.TextColumn("Enter Uzio Location", required=False)},
        hide_index=True, use_container_width=True, key="adp_sanity_loc_editor"
    )
    
    loc_dict = dict(zip(edited_locs['Source Work Location'], edited_locs['Mapped Uzio Work Location']))

    st.markdown("---")
    
    from utils.audit_utils import validate_source_data
    validation = validate_source_data(df_adp, resolved_field_map)

    hard_errors = validation['hard_errors']
    flsa_corrections = validation['flsa_corrections']
    flsa_blanks = validation['flsa_blanks']
    intern_corrections = validation['intern_corrections']
    email_fallbacks = validation['email_fallbacks']
    anomalies = validation.get('anomalies', pd.DataFrame())

    has_soft_warnings = not flsa_corrections.empty or not flsa_blanks.empty or not intern_corrections.empty or not email_fallbacks.empty or not anomalies.empty
    if has_soft_warnings:
        with st.expander("System Minor Warnings & Mapping Suggestions", expanded=False):
            st.info("💡 **Note:** Suggestions can be automatically applied using the checkpoints above.")
            if not flsa_corrections.empty: st.markdown(f"- ℹ️ **FLSA Mismatches:** {len(flsa_corrections)} employee(s).")
            if not flsa_blanks.empty: st.markdown(f"- ⚠️ **Blank FLSA:** {len(flsa_blanks)} employee(s).")
            if not anomalies.empty: st.markdown(f"- ⚠️ **FLSA Anomalies:** {len(anomalies)} employee(s).")
            if not intern_corrections.empty: st.markdown(f"- ⚠️ **Intern Codes:** {len(intern_corrections)} employee(s).")

    if not hard_errors.empty:
        st.error(f"**⛔ {len(hard_errors)} Critical Error(s) Found!**")
        with st.expander("View Details", expanded=False):
            st.dataframe(hard_errors, hide_index=True, use_container_width=True)
    else:
        st.success("✅ Source data passed critical checks!")

    if st.button("Download Corrected Source"):
        df_download = df_adp.copy()
        
        # Apply Fixes
        if fix_options.get('fix_emails'):
            c_work = resolved_field_map.get('Work Email')
            c_pers = resolved_field_map.get('Personal Email')
            if c_work and c_pers and c_work in df_download.columns and c_pers in df_download.columns:
                mask = df_download[c_work].isna() | (df_download[c_work].astype(str).str.strip() == "")
                df_download.loc[mask, c_work] = df_download.loc[mask, c_pers]

        if fix_options.get('fix_dol_status'):
            col_dol = next((c for c in df_download.columns if str(c).lower().strip().replace('_',' ') == 'dol status' or 'worker category description' in str(c).lower()), None)
            if col_dol:
                mask_blank = df_download[col_dol].isna() | (df_download[col_dol].astype(str).str.strip() == "")
                df_download.loc[mask_blank, col_dol] = "Full Time"

        if fix_options.get('fix_job_title'):
            c_jt = resolved_field_map.get('Job Title')
            c_dept = resolved_field_map.get('Department')
            if c_jt and c_dept and c_jt in df_download.columns and c_dept in df_download.columns:
                mask_jt = df_download[c_jt].isna() | (df_download[c_jt].astype(str).str.strip().lower() == "nan") | (df_download[c_jt].astype(str).str.strip() == "")
                df_download.loc[mask_jt, c_jt] = df_download.loc[mask_jt, c_dept]

        # Apply Mappings to download file
        if src_loc_col and src_loc_col in df_download.columns:
            df_download[src_loc_col] = df_download[src_loc_col].astype(str).str.strip().map(lambda x: loc_dict.get(x, x))

        # Standardize ALL Date Columns to MM/DD/YYYY
        date_cols = [
            resolved_field_map.get('Hire Date'),          # Hire/Rehire Date
            resolved_field_map.get('Original Hire Date'), # Hire Date
            resolved_field_map.get('Termination Date'),   # Termination Date
            resolved_field_map.get('DOB'),                # Birth Date
        ]
        date_cols = [c for c in date_cols if c is not None]
        df_download = format_datetime_strings(df_download, date_cols)

        if sort_by_manager and col_sup_code and col_sup_code in df_download.columns:
            emp_id_col = resolved_field_map.get('Employee ID')
            if emp_id_col and emp_id_col in df_download.columns:
                sup_counts = df_download[df_download[col_sup_code].notna()][col_sup_code].value_counts().to_dict()
                df_download['__mgr_sort'] = df_download[emp_id_col].astype(str).str.strip().map(lambda x: sup_counts.get(x, 0))
                df_download = df_download.sort_values(by='__mgr_sort', ascending=False).drop(columns=['__mgr_sort'])

        if not hard_errors.empty:
            emp_id_col = resolved_field_map.get('Employee ID')
            if emp_id_col and emp_id_col in df_download.columns:
                error_map = dict(zip(hard_errors['Employee ID'].astype(str), hard_errors['Issue']))
                df_download.insert(0, 'CRITICAL_WARNINGS', df_download[emp_id_col].astype(str).map(error_map).fillna(""))

        restored_cols = [norm_to_orig.get(c, c) for c in df_download.columns if c in norm_to_orig]
        if 'CRITICAL_WARNINGS' in df_download.columns: df_download.columns = ['CRITICAL_WARNINGS'] + restored_cols
        else: df_download.columns = restored_cols

        corrected_xlsx = io.BytesIO()
        df_download.to_excel(corrected_xlsx, index=False)
        corrected_xlsx.seek(0)
        st.download_button("📥 Download Corrected Source (XLSX)", corrected_xlsx.getvalue(), f"ADP_Cleaned_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx")

def render_census_generator():
    st.title("ADP - Full Census Generation")
    
    adp_file = st.file_uploader("Upload ADP Census Export", type=["xlsx", "csv"], key="adp_gen_upload")
    if not adp_file: return

    df_adp, _, _, resolved_field_map = preprocess_adp_file(adp_file)
    if df_adp is None: return

    fix_options = render_auto_fix_options("adp_gen")
    
    src_job_col = resolved_field_map.get('Job Title')
    src_loc_col = resolved_field_map.get('Work Location')
    unique_jobs = sorted([str(j).strip() for j in df_adp[src_job_col].dropna().unique()]) if src_job_col else []
    unique_locs = sorted([str(l).strip() for l in df_adp[src_loc_col].dropna().unique()]) if src_loc_col else []

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Job Title Mapping**")
        edited_jobs = st.data_editor(
            pd.DataFrame({"Source Job Title": unique_jobs, "Mapped Uzio Job Title": [None]*len(unique_jobs)}),
            column_config={"Mapped Uzio Job Title": st.column_config.SelectboxColumn("Select Uzio Role", options=ALLOWED_JOB_TITLES, required=True)},
            hide_index=True, use_container_width=True, key="adp_job_editor"
        )
    with col2:
        st.write("**Work Location Mapping**")
        edited_locs = st.data_editor(
            pd.DataFrame({"Source Work Location": unique_locs, "Mapped Uzio Work Location": [""]*len(unique_locs)}),
            column_config={"Mapped Uzio Work Location": st.column_config.TextColumn("Enter Uzio Location", required=True)},
            hide_index=True, use_container_width=True, key="adp_loc_editor"
        )

    if st.button("Generate Uzio Template", type="primary"):
        with st.spinner("Processing..."):
            try:
                job_dict = dict(zip(edited_jobs['Source Job Title'], edited_jobs['Mapped Uzio Job Title']))
                loc_dict = dict(zip(edited_locs['Source Work Location'], edited_locs['Mapped Uzio Work Location']))
                
                df_uzio = generate_uzio_template(df_adp, resolved_field_map, fix_options=fix_options)
                
                if src_job_col: df_uzio['Job Title'] = df_adp[src_job_col].astype(str).str.strip().map(job_dict).fillna(df_adp[src_job_col])
                if src_loc_col: df_uzio['Work Location'] = df_adp[src_loc_col].astype(str).str.strip().map(loc_dict).fillna(df_adp[src_loc_col])

                from utils.audit_utils import inject_into_uzio_template
                wb = inject_into_uzio_template(df_uzio, template_path="templates/Uzio_Census_Template.xlsm")
                out = io.BytesIO()
                wb.save(out)
                out.seek(0)

                st.success("Template Generated!")
                st.download_button("Download Uzio Template", out.getvalue(), f"Uzio_ADP_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsm")
            except Exception as e:
                st.error(f"Error: {e}")

def render_selective_census_generator():
    st.title("ADP - Selective Census Sync")
    
    adp_file = st.file_uploader("Upload ADP Census Export", type=["xlsx", "csv"], key="adp_sel_upload")
    if not adp_file: return

    df_adp, _, _, resolved_field_map = preprocess_adp_file(adp_file)
    if df_adp is None: return

    fix_options = render_auto_fix_options("adp_sel")
    
    from utils.audit_utils import UZIO_RAW_MAPPING, read_uzio_raw_file, extract_mappings_from_uzio
    selected_uzio_cols = st.multiselect("🎯 Select Uzio Columns to Sync", options=list(UZIO_RAW_MAPPING.keys()), default=["Employee SSN"])
    
    uzio_template_file = st.file_uploader("📤 Upload Pre-filled Uzio Template (.xlsm)", type=["xlsm"], key="adp_uzio_template_sel")
    
    job_seeds, loc_seeds = {}, {}
    if uzio_template_file:
        df_seeds = read_uzio_raw_file(uzio_template_file)
        if df_seeds is not None: job_seeds, loc_seeds = extract_mappings_from_uzio(df_adp, df_seeds, resolved_field_map)
        uzio_template_file.seek(0)

    src_job_col = resolved_field_map.get('Job Title')
    src_loc_col = resolved_field_map.get('Work Location')
    unique_jobs = sorted([str(j).strip() for j in df_adp[src_job_col].dropna().unique()]) if src_job_col else []
    unique_locs = sorted([str(l).strip() for l in df_adp[src_loc_col].dropna().unique()]) if src_loc_col else []

    col1, col2 = st.columns(2)
    with col1:
        edited_jobs = st.data_editor(
            pd.DataFrame({"Source Job Title": unique_jobs, "Mapped Uzio Job Title": [job_seeds.get(j) for j in unique_jobs]}),
            column_config={"Mapped Uzio Job Title": st.column_config.SelectboxColumn("Select Uzio Role", options=ALLOWED_JOB_TITLES, required=True)},
            hide_index=True, use_container_width=True, key="adp_job_editor_sel"
        )
    with col2:
        edited_locs = st.data_editor(
            pd.DataFrame({"Source Work Location": unique_locs, "Mapped Uzio Work Location": [loc_seeds.get(l, "") for l in unique_locs]}),
            column_config={"Mapped Uzio Work Location": st.column_config.TextColumn("Enter Uzio Location", required=True)},
            hide_index=True, use_container_width=True, key="adp_loc_editor_sel"
        )

    if st.button("Update Uzio Template", type="primary"):
        if not uzio_template_file: return st.error("Upload Uzio Template first.")
        with st.spinner("Processing..."):
            try:
                from utils.audit_utils import read_uzio_template_df, selective_update_uzio
                df_template = read_uzio_template_df(uzio_template_file)
                df_uzio, summary, _ = selective_update_uzio(df_adp, df_template, selected_uzio_cols, resolved_field_map, fix_options=fix_options)
                
                # Apply Mappings
                job_dict = dict(zip(edited_jobs['Source Job Title'], edited_jobs['Mapped Uzio Job Title']))
                loc_dict = dict(zip(edited_locs['Source Work Location'], edited_locs['Mapped Uzio Work Location']))
                if src_job_col: df_uzio['Job Title'] = df_adp[src_job_col].astype(str).str.strip().map(job_dict).fillna(df_adp[src_job_col])
                if src_loc_col: df_uzio['Work Location'] = df_adp[src_loc_col].astype(str).str.strip().map(loc_dict).fillna(df_adp[src_loc_col])

                from utils.audit_utils import inject_into_uzio_template
                uzio_template_file.seek(0)
                wb = inject_into_uzio_template(df_uzio, uzio_template_file)
                out = io.BytesIO()
                wb.save(out)
                out.seek(0)

                st.success(summary)
                st.download_button("Download Updated Template", out.getvalue(), f"Uzio_Updated_ADP_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsm")
            except Exception as e:
                st.error(f"Error: {e}")

def render_ui():
    st.sidebar.title("Census Tools")
    tool = st.sidebar.selectbox("Select Tool", ["Sanity Check", "Full Generation", "Selective Sync"], key="adp_tool_select")
    if tool == "Sanity Check": render_census_sanity_check()
    elif tool == "Full Generation": render_census_generator()
    else: render_selective_census_generator()
