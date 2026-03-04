import io
import pandas as pd
import streamlit as st
from utils.audit_utils import generate_uzio_template

APP_TITLE = "Paycom to Uzio Census Template Generator"

PAYCOM_FIELD_MAP = {
    'Employee ID': ['Employee_Code', 'Employee Code', 'EE Code'],
    'First Name': ['Legal_Firstname', 'First Name', 'Legal First Name'],
    'Last Name': ['Legal_Lastname', 'Last Name', 'Legal Last Name'],
    'Middle Initial': ['Legal_Middle_Name', 'Middle Name', 'Middle Initial'],
    'Employment Status': ['Employee_Status', 'Status', 'EE Status', 'Employment Status'],
    'Employment Type': ['Employment Type', 'EE Type', 'Employee Type'],
    'Hire Date': ['Most_Recent_Hire_Date', 'Hire Date', 'Recent Hire Date'],
    'Termination Date': ['Termination_Date', 'Termination Date'],
    'Termination Reason': ['Termination_Reason', 'Termination Reason', 'Term Reason', 'Reason'],
    'Pay Type': ['Pay_Type', 'Pay Type'],
    'Annual Salary': ['Annual_Salary', 'Annual Salary'],
    'Hourly Pay Rate': ['Rate_1', 'Hourly Rate', 'Pay Rate', 'Rate 1'],
    'Working Hours': ['Scheduled_Pay_Period_Hours', 'Scheduled Hours', 'Working Hours'],
    'Job Title': ['Department_Desc', 'Position', 'Job Title'],
    'Department': ['Department_Desc', 'Department', 'Department Desc'],
    'Work Email': ['Work_Email', 'Work Email', 'Email'],
    'Personal Email': ['Personal_Email', 'Personal Email'],
    'Phone Number': ['Primary_Phone', 'Phone Number', 'Phone'],
    'SSN': ['SS_Number', 'SSN', 'Social Security Number'],
    'DOB': ['Birth_Date_(MM/DD/YYYY)', 'Birth Date', 'DOB'],
    'Gender': ['Gender', 'Sex'],
    'Tobacco User': ['Tobacco_User', 'Tobacco User'],
    'FLSA Classification': ['Exempt_Status', 'FLSA Status', 'FLSA Classification'],
    'Address Line 1': ['Primary_Address_Line_1', 'Address Line 1'],
    'Address Line 2': ['Primary_Address_Line_2', 'Address Line 2'],
    'City': ['Primary_City/Municipality', 'City'],
    'Zip': ['Primary_Zip/Postal_Code', 'Zip', 'Zip Code'],
    'State': ['Primary_State/Province', 'State'],
    'Mailing Address Line 1': ['Mailing_Address_Line_1', 'Mailing Address Line 1'],
    'Mailing Address Line 2': ['Mailing_Address_Line_2', 'Mailing Address Line 2'],
    'Mailing City': ['Mailing_City/Municipality', 'Mailing City'],
    'Mailing Zip': ['Mailing_Zip/Postal_Code', 'Mailing Zip'],
    'Mailing State': ['Mailing_State/Province', 'Mailing State'],
    'License Number': ['DriversLicense', 'Drivers License', 'License Number'],
    'Work Location': ['Work_Location', 'Location', 'Work Location']
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
    c = c.replace("\u2019", "'").replace("\u201C", '"').replace("\u201D", '"')
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "")
    c = c.strip('"').strip("'")
    return c.lower()

def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    **Instructions**:
    1. Upload your **Paycom Census Export** (.csv or .xlsx).
    2. Map your **Job Titles** and **Work Locations** in the tables below.
    3. Click **Generate Uzio Template**.
    4. Download the correctly formatted Uzio `.xlsx` file.
    """)
    
    paycom_file = st.file_uploader("Upload Paycom Census Export", type=["xlsx", "csv"], key="pc_gen_upload")
    
    if not paycom_file:
        return
    
    # --- STEP 1: Read and process the source file (runs on every rerun) ---
    try:
        if paycom_file.name.lower().endswith('.csv'):
            try:
                df_paycom = pd.read_csv(paycom_file, dtype=str)
            except UnicodeDecodeError:
                paycom_file.seek(0)
                df_paycom = pd.read_csv(paycom_file, dtype=str, encoding='latin1')
        else:
            df_paycom = pd.read_excel(paycom_file, dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return
        
    # Save original column headers before normalization
    original_columns = list(df_paycom.columns)
    
    # Normalize source columns
    df_paycom.columns = [norm_colname(c) for c in df_paycom.columns]
    
    # Build mapping: normalized -> original (for restoring headers on download)
    norm_to_orig = dict(zip(df_paycom.columns, original_columns))
    
    # Resolve field map
    resolved_field_map = {}
    for std_name, vendor_cols in PAYCOM_FIELD_MAP.items():
        found = False
        for vc in vendor_cols:
            norm_vc = norm_colname(vc)
            if norm_vc in df_paycom.columns:
                resolved_field_map[std_name] = norm_vc
                found = True
                break
        if not found:
            resolved_field_map[std_name] = norm_colname(vendor_cols[0])
            
    # --- PAYCOM SPECIFIC PRE-PROCESSING & VALIDATION ---
    paycom_custom_errors = []
    paycom_pos_fixes = []
    
    # Identify exact columns (normalized to lowercase)
    col_dol = 'dol_status' if 'dol_status' in df_paycom.columns else None
    col_pos = 'position' if 'position' in df_paycom.columns else None
    
    col_dep = None
    for cand in ['department_desc', 'department_dec', 'department', 'department_description', 'labor_allocation_details', 'delivery_station_code_desc']:
        if cand in df_paycom.columns:
            col_dep = cand
            break
    
    # Find employee status column - check variations
    col_emp_status = None
    for cand in ['employee_status', 'employee status', 'employment status', 'status', 'ee status']:
        if cand in df_paycom.columns:
            col_emp_status = cand
            break
            
    for idx, row in df_paycom.iterrows():
        emp_ref = f"Row {idx+2}"
        if 'employee_code' in df_paycom.columns and pd.notna(row.get('employee_code')) and str(row.get('employee_code')).strip():
            emp_ref = str(row.get('employee_code')).strip()
        elif 'employee code' in df_paycom.columns and pd.notna(row.get('employee code')) and str(row.get('employee code')).strip():
            emp_ref = str(row.get('employee code')).strip()
            
        custom_missing = []
        
        # 1. DOL_Status blank check
        if col_dol:
            val_dol = row.get(col_dol)
            if pd.isna(val_dol) or str(val_dol).strip() == "":
                custom_missing.append("DOL_Status is blank")
                
        # 2. Employee Status blank check (Hard stop enforcement)
        if col_emp_status:
            val_emp = row.get(col_emp_status)
            if pd.isna(val_emp) or str(val_emp).strip() == "":
                custom_missing.append("Employee Status is blank")
                
        # 3. Position and Department Desc check
        if col_pos:
            val_pos = row.get(col_pos)
            if pd.isna(val_pos) or str(val_pos).strip() == "":
                # Position is blank, check department_desc
                if col_dep:
                    val_dep = row.get(col_dep)
                    if pd.notna(val_dep) and str(val_dep).strip() != "":
                        # Fill position with department_desc
                        df_paycom.at[idx, col_pos] = str(val_dep).strip()
                        paycom_pos_fixes.append({
                            'Employee ID': emp_ref,
                            'Original Position': '(blank)',
                            'Fixed Value': str(val_dep).strip(),
                            'Source Column': norm_to_orig.get(col_dep, col_dep)
                        })
                    else:
                        # Both blank
                        custom_missing.append(f"Position is blank (and fallback '{norm_to_orig.get(col_dep, col_dep)}' is also blank)")
                else:
                    custom_missing.append("Position is blank")
                    
        if custom_missing:
            paycom_custom_errors.append({
                'Employee ID': emp_ref,
                'Issue': ", ".join(custom_missing)
            })
            
    # --- CHECK: State column must exist ---
    state_col = resolved_field_map.get('State')
    if not state_col or state_col not in df_paycom.columns:
        st.error("**⛔ 'Primary_State/Province' (or similar State) column not found in the source file!** This column is required for state validation.")
        return
    
    # --- CHECK: Zip column must exist ---
    zip_col = resolved_field_map.get('Zip')
    if not zip_col or zip_col not in df_paycom.columns:
        st.error("**⛔ 'Primary_Zip/Postal_Code' (or similar Zip) column not found in the source file!** This column is required for zip code validation.")
        return
    
    # --- PRE-GENERATION SANITY CHECKS ---
    from utils.audit_utils import validate_source_data
    validation = validate_source_data(df_paycom, resolved_field_map)
    
    # Merge custom Paycom hard errors with generic hard errors
    hard_errors_df = validation['hard_errors']
    if paycom_custom_errors:
        df_custom = pd.DataFrame(paycom_custom_errors)
        if not hard_errors_df.empty:
            # Group by Employee ID to merge issues
            hard_errors = pd.concat([hard_errors_df, df_custom]).groupby('Employee ID')['Issue'].apply(lambda x: ', '.join(x)).reset_index()
        else:
            hard_errors = df_custom
    else:
        hard_errors = hard_errors_df
        
    flsa_corrections = validation['flsa_corrections']
    flsa_blanks = validation['flsa_blanks']
    intern_corrections = validation['intern_corrections']
    email_fallbacks = validation['email_fallbacks']
    
    # Show soft warnings first (non-blocking)
    if paycom_pos_fixes:
        st.info(f"**Position Auto-Fill:** {len(paycom_pos_fixes)} employee(s) had a blank Position, but it was automatically filled using their Department Description.")
        with st.expander("View Position Fixes", expanded=False):
            st.dataframe(pd.DataFrame(paycom_pos_fixes), hide_index=True, use_container_width=True)
            
    if not flsa_corrections.empty:
        st.info(f"**FLSA Auto-Corrections:** {len(flsa_corrections)} employee(s) had mismatched FLSA classifications. These have been auto-corrected.")
        with st.expander("View FLSA Corrections", expanded=False):
            st.dataframe(flsa_corrections, hide_index=True, use_container_width=True)
    
    if not flsa_blanks.empty:
        st.warning(f"**Blank FLSA Classification:** {len(flsa_blanks)} employee(s) have a Pay Type set but FLSA Classification is blank. Please verify.")
        with st.expander("View Blank FLSA Details", expanded=False):
            st.dataframe(flsa_blanks, hide_index=True, use_container_width=True)
    
    if not intern_corrections.empty:
        st.warning(f"**Intern → Part Time:** {len(intern_corrections)} employee(s) had 'Intern' as Worker Category. Employment Type has been changed to **Part Time** in the output.")
        with st.expander("View Intern Corrections", expanded=False):
            st.dataframe(intern_corrections, hide_index=True, use_container_width=True)
    
    if not email_fallbacks.empty:
        st.info(f"**Email Fallback:** {len(email_fallbacks)} employee(s) had blank Work Email. Personal Email was used instead.")
        with st.expander("View Email Fallbacks", expanded=False):
            st.dataframe(email_fallbacks, hide_index=True, use_container_width=True)
    
    # Show hard errors (non-blocking — user can still proceed)
    if not hard_errors.empty:
        st.error(f"**⛔ {len(hard_errors)} Critical Error(s) Found in Source Data!** You can fix these manually, use Auto-Fix below, or proceed as-is.")
        
        # --- Summary breakdown by issue type ---
        all_issues = []
        for issues_str in hard_errors['Issue']:
            for issue in str(issues_str).split(", "):
                import re
                clean = re.sub(r"\s*\(.*?\)", "", issue).strip()
                if clean:
                    all_issues.append(clean)
        
        from collections import Counter
        issue_counts = Counter(all_issues)
        
        st.markdown("**Summary:**")
        for issue, count in issue_counts.most_common():
            st.markdown(f"- **{count}** employee(s): {issue}")
        
        # Full details in expander
        with st.expander(f"View All {len(hard_errors)} Error Details", expanded=False):
            st.dataframe(hard_errors, hide_index=True, use_container_width=True)
        
        err_csv = io.BytesIO()
        hard_errors.to_csv(err_csv, index=False)
        err_csv.seek(0)
        st.download_button(
            label="Download Error Report (CSV)",
            data=err_csv.getvalue(),
            file_name=f"Source_Validation_Errors_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            key="pc_hard_err_dl"
        )
    else:
        st.success("✅ Source data passed all sanity checks!")
    
    # --- AUTO-FIX OPTIONS (always shown, checkbox-based) ---
    from utils.preprocess_source_data import detect_fixable_issues, apply_auto_fixes
    fixable = detect_fixable_issues(df_paycom, resolved_field_map)
    
    has_any_fixable = (fixable['flsa_blank_count'] > 0 or fixable['email_blank_count'] > 0 
                       or fixable['zip_fixable_count'] > 0 or fixable['hours_blank_count'] > 0)
    
    if has_any_fixable:
        st.markdown("---")
        st.markdown("### 🔧 Auto-Fix Options")
        st.markdown("Select which issues you'd like the tool to fix automatically:")
        
        fix_flsa = False
        fix_email = False
        fix_zip = False
        fix_hours = False
        
        if fixable['flsa_blank_count'] > 0:
            fix_flsa = st.checkbox(
                f"**Fix Blank FLSA Classification** — Set based on Pay Type ({fixable['flsa_blank_count']} employee(s) affected)",
                value=True, key="pc_fix_flsa"
            )
        
        if fixable['email_blank_count'] > 0:
            fix_email = st.checkbox(
                f"**Fix Blank Work Email** — Use Personal Email as fallback ({fixable['email_blank_count']} employee(s) affected)",
                value=True, key="pc_fix_email"
            )
        
        if fixable['zip_fixable_count'] > 0:
            fix_zip = st.checkbox(
                f"**Fix Zip Code Issues** — Strip after dash, zero-pad to 5 digits ({fixable['zip_fixable_count']} employee(s) affected)",
                value=True, key="pc_fix_zip"
            )
        
        if fixable['hours_blank_count'] > 0:
            label = f"**Fix Blank Working Hours** — Set to 0 ({fixable['hours_blank_count']} employee(s) affected)"
            if fixable['hours_col_missing']:
                label = f"**Fix Missing Working Hours Column** — Add column with 0 values ({fixable['hours_blank_count']} employee(s) affected)"
            fix_hours = st.checkbox(label, value=True, key="pc_fix_hours")
        
        # --- Optional Mapping Checkboxes ---
        src_job_col_af = resolved_field_map.get('Job Title')
        src_loc_col_af = resolved_field_map.get('Work Location')
        
        unique_jobs_af = []
        if src_job_col_af and src_job_col_af in df_paycom.columns:
            unique_jobs_af = sorted([str(j).strip() for j in df_paycom[src_job_col_af].dropna().unique() if str(j).strip()])
        
        unique_locs_af = []
        if src_loc_col_af and src_loc_col_af in df_paycom.columns:
            unique_locs_af = sorted([str(l).strip() for l in df_paycom[src_loc_col_af].dropna().unique() if str(l).strip()])
        
        fix_job_mapping = False
        fix_loc_mapping = False
        edited_jobs_af = None
        edited_locs_af = None
        
        if unique_jobs_af:
            fix_job_mapping = st.checkbox(
                f"**Map Job Titles** — Map {len(unique_jobs_af)} unique Job Title(s) to Uzio format",
                value=False, key="pc_fix_jobs"
            )
        
        if unique_locs_af:
            fix_loc_mapping = st.checkbox(
                f"**Map Work Locations** — Map {len(unique_locs_af)} unique Work Location(s) to Uzio format",
                value=False, key="pc_fix_locs"
            )
        
        # Show mapping editors if checked
        if fix_job_mapping:
            st.write("**Job Title Mapping**")
            df_job_map_af = pd.DataFrame({"Source Job Title": unique_jobs_af, "Mapped Uzio Job Title": pd.Series([None]*len(unique_jobs_af), dtype="object")})
            edited_jobs_af = st.data_editor(
                df_job_map_af,
                column_config={
                    "Source Job Title": st.column_config.Column(disabled=True),
                    "Mapped Uzio Job Title": st.column_config.SelectboxColumn("Select Uzio Role", options=ALLOWED_JOB_TITLES, required=True)
                },
                hide_index=True, use_container_width=True, key="pc_af_job_editor"
            )
        
        if fix_loc_mapping:
            st.write("**Work Location Mapping**")
            df_loc_map_af = pd.DataFrame({"Source Work Location": unique_locs_af, "Mapped Uzio Work Location": pd.Series([""]*len(unique_locs_af), dtype=str)})
            edited_locs_af = st.data_editor(
                df_loc_map_af,
                column_config={
                    "Source Work Location": st.column_config.Column(disabled=True),
                    "Mapped Uzio Work Location": st.column_config.TextColumn("Enter Uzio Location", required=True)
                },
                hide_index=True, use_container_width=True, key="pc_af_loc_editor"
            )
        
        if st.button("🔧 Apply Selected Fixes", type="primary", key="pc_autofix_btn"):
            fixes_to_apply = {
                'fix_flsa': fix_flsa,
                'fix_email': fix_email,
                'fix_zip': fix_zip,
                'fix_hours': fix_hours
            }
            
            if not any(fixes_to_apply.values()):
                st.warning("No fixes selected. Please check at least one option above.")
            else:
                fixes = apply_auto_fixes(df_paycom, resolved_field_map, fixes_to_apply)
                
                # Display what was fixed
                fix_count = 0
                if not fixes['flsa_fills'].empty:
                    fix_count += len(fixes['flsa_fills'])
                    st.info(f"**FLSA Auto-Fill:** {len(fixes['flsa_fills'])} employee(s) had blank FLSA — filled based on Pay Type.")
                    with st.expander("View FLSA Auto-Fills", expanded=False):
                        st.dataframe(fixes['flsa_fills'], hide_index=True, use_container_width=True)
                
                if not fixes['email_fallbacks'].empty:
                    fix_count += len(fixes['email_fallbacks'])
                    st.info(f"**Email Fallback:** {len(fixes['email_fallbacks'])} employee(s) had blank Work Email — filled from Personal Email.")
                    with st.expander("View Email Fallbacks", expanded=False):
                        st.dataframe(fixes['email_fallbacks'], hide_index=True, use_container_width=True)
                
                if not fixes['zip_corrections'].empty:
                    fix_count += len(fixes['zip_corrections'])
                    st.info(f"**Zip Code Corrections:** {len(fixes['zip_corrections'])} employee(s) had zip codes normalized.")
                    with st.expander("View Zip Corrections", expanded=False):
                        st.dataframe(fixes['zip_corrections'], hide_index=True, use_container_width=True)
                
                if not fixes['hours_fixes'].empty:
                    fix_count += len(fixes['hours_fixes'])
                    st.info(f"**Working Hours Fix:** {len(fixes['hours_fixes'])} employee(s) had blank Working Hours set to 0.")
                    with st.expander("View Working Hours Fixes", expanded=False):
                        st.dataframe(fixes['hours_fixes'], hide_index=True, use_container_width=True)
                
                # Apply mapping fixes if selected
                if fix_job_mapping and edited_jobs_af is not None and src_job_col_af and src_job_col_af in df_paycom.columns:
                    job_dict_af = dict(zip(edited_jobs_af['Source Job Title'], edited_jobs_af['Mapped Uzio Job Title']))
                    stripped_jobs = df_paycom[src_job_col_af].astype(str).str.strip()
                    df_paycom[src_job_col_af] = stripped_jobs.map(job_dict_af).fillna(df_paycom[src_job_col_af])
                    fix_count += 1
                    st.info(f"**Job Title Mapping:** Applied mapping for {len(job_dict_af)} unique job title(s).")
                
                if fix_loc_mapping and edited_locs_af is not None and src_loc_col_af and src_loc_col_af in df_paycom.columns:
                    loc_dict_af = dict(zip(edited_locs_af['Source Work Location'], edited_locs_af['Mapped Uzio Work Location']))
                    stripped_locs = df_paycom[src_loc_col_af].astype(str).str.strip()
                    df_paycom[src_loc_col_af] = stripped_locs.map(loc_dict_af).fillna(df_paycom[src_loc_col_af])
                    fix_count += 1
                    st.info(f"**Work Location Mapping:** Applied mapping for {len(loc_dict_af)} unique location(s).")
                
                if fix_count > 0:
                    st.success(f"✅ {fix_count} fix(es) applied successfully!")
                    
                    # Restore original column headers for the download
                    df_download = df_paycom.copy()
                    restored_cols = [norm_to_orig.get(c, c) for c in df_download.columns]
                    df_download.columns = restored_cols
                    
                    # Provide corrected source file for download (CSV and XLSX)
                    st.markdown("**Download Corrected Source File:**")
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        corrected_csv = io.BytesIO()
                        df_download.to_csv(corrected_csv, index=False)
                        corrected_csv.seek(0)
                        st.download_button(
                            label="📥 Download Corrected Source (CSV)",
                            data=corrected_csv.getvalue(),
                            file_name=f"Paycom_Corrected_Source_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                            mime="text/csv",
                            key="pc_corrected_csv_dl"
                        )
                    with dl_col2:
                        corrected_xlsx = io.BytesIO()
                        df_download.to_excel(corrected_xlsx, index=False, engine='openpyxl')
                        corrected_xlsx.seek(0)
                        st.download_button(
                            label="📥 Download Corrected Source (XLSX)",
                            data=corrected_xlsx.getvalue(),
                            file_name=f"Paycom_Corrected_Source_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="pc_corrected_xlsx_dl"
                        )
                else:
                    st.warning("No auto-fixable issues were found for the selected options.")
    
    st.markdown("---")
    st.markdown("### Step 2: Map Data to Uzio Format")
    st.markdown("Please map the unique Job Titles and Work Locations found in your source file to the acceptable Uzio formats.")
    
    src_job_col = resolved_field_map.get('Job Title')
    src_loc_col = resolved_field_map.get('Work Location')
    
    # Extract unique Jobs
    unique_jobs = []
    if src_job_col and src_job_col in df_paycom.columns:
        unique_jobs = sorted([str(j).strip() for j in df_paycom[src_job_col].dropna().unique() if str(j).strip()])
        
    # Extract unique Locations
    unique_locs = []
    if src_loc_col and src_loc_col in df_paycom.columns:
        unique_locs = sorted([str(l).strip() for l in df_paycom[src_loc_col].dropna().unique() if str(l).strip()])
        
    # Create mapping dataframes for the editor
    df_job_map = pd.DataFrame({"Source Job Title": unique_jobs, "Mapped Uzio Job Title": pd.Series([None]*len(unique_jobs), dtype="object")})
    df_loc_map = pd.DataFrame({"Source Work Location": unique_locs, "Mapped Uzio Work Location": pd.Series([""]*len(unique_locs), dtype=str)})

    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Job Title Mapping**")
        edited_jobs = st.data_editor(
            df_job_map, 
            column_config={
                "Source Job Title": st.column_config.Column(disabled=True),
                "Mapped Uzio Job Title": st.column_config.SelectboxColumn("Select Uzio Role", options=ALLOWED_JOB_TITLES, required=True)
            },
            hide_index=True,
            use_container_width=True,
            key="pc_job_editor"
        )
    
    with col2:
        st.write("**Work Location Mapping**")
        edited_locs = st.data_editor(
            df_loc_map,
            column_config={
                "Source Work Location": st.column_config.Column(disabled=True),
                "Mapped Uzio Work Location": st.column_config.TextColumn("Enter Uzio Location", required=True)
            },
            hide_index=True,
            use_container_width=True,
            key="pc_loc_editor"
        )
    
    # Check if mapping is completely filled out
    job_map_complete = not edited_jobs['Mapped Uzio Job Title'].isna().any() if not edited_jobs.empty else True
    loc_map_complete = not edited_locs['Mapped Uzio Work Location'].isna().any() and not (edited_locs['Mapped Uzio Work Location'] == "").any() if not edited_locs.empty else True
    
    if not job_map_complete or not loc_map_complete:
        st.warning("Please fill out all mappings in the tables above before generating the template.")
        return
        
    # --- DSP OWNER DETECTION ---
    col_sup_code = None
    for cand in ['supervisor_primary_code', 'supervisor primary code', 'supervisorcode']:
        if cand in df_paycom.columns:
            col_sup_code = cand
            break
            
    detected_dsp_id = None
    detected_dsp_name = ""
    
    if col_sup_code:
        # Filter out blanks
        valid_sups = df_paycom[df_paycom[col_sup_code].notna() & (df_paycom[col_sup_code].astype(str).str.strip() != "")]
        if not valid_sups.empty:
            sup_counts = valid_sups[col_sup_code].value_counts()
            if not sup_counts.empty:
                detected_dsp_id = str(sup_counts.index[0]).strip()
                
                # Try to get their name
                emp_code_col = resolved_field_map.get('Employee ID')
                if emp_code_col and emp_code_col in df_paycom.columns:
                    match = df_paycom[df_paycom[emp_code_col].astype(str).str.strip() == detected_dsp_id]
                    if not match.empty:
                        fn = match.iloc[0].get(resolved_field_map.get('First Name'), '')
                        ln = match.iloc[0].get(resolved_field_map.get('Last Name'), '')
                        if pd.notna(fn) and pd.notna(ln):
                            detected_dsp_name = f"{str(fn).strip()} {str(ln).strip()}".strip()

    st.markdown("---")
    st.markdown("### Step 3: Finalize & Generate")
    
    set_dsp_owner = False
    if detected_dsp_id:
        name_disp = f" ({detected_dsp_name})" if detected_dsp_name else ""
        st.info(f"**DSP Owner Detected:** Employee **{detected_dsp_id}**{name_disp} supervises the most employees.")
        set_dsp_owner = st.checkbox(
            f"Automatically set Position to **'DSP Owner'** for Employee {detected_dsp_id} and move them to the **very top** of the census.",
            value=True, key="pc_set_dsp_owner"
        )
    
    # --- STEP 4: Generate Template (only on button click) ---
    if st.button("Generate Uzio Template", type="primary", key="pc_gen_btn"):
        with st.spinner("Generating..."):
            try:
                # Generate Uzio Template
                df_uzio = generate_uzio_template(df_paycom, resolved_field_map)
                
                # Apply Job Title Mapping
                if src_job_col and src_job_col in df_paycom.columns:
                    job_dict = dict(zip(edited_jobs['Source Job Title'], edited_jobs['Mapped Uzio Job Title']))
                    stripped_jobs = df_paycom[src_job_col].astype(str).str.strip()
                    df_uzio['Job Title'] = stripped_jobs.map(job_dict).fillna(df_paycom[src_job_col])
                    
                # Apply Work Location Mapping
                if src_loc_col and src_loc_col in df_paycom.columns:
                    loc_dict = dict(zip(edited_locs['Source Work Location'], edited_locs['Mapped Uzio Work Location']))
                    stripped_locs = df_paycom[src_loc_col].astype(str).str.strip()
                    df_uzio['Work Location'] = stripped_locs.map(loc_dict).fillna(df_paycom[src_loc_col])
                    
                # Apply DSP Owner Override & Sort
                if set_dsp_owner and detected_dsp_id:
                    emp_id_col_uzio = 'Employee ID*' if 'Employee ID*' in df_uzio.columns else 'Employee ID'
                    if emp_id_col_uzio in df_uzio.columns:
                        # Ensure emp_id is string
                        df_uzio_id_str = df_uzio[emp_id_col_uzio].astype(str).str.strip()
                        dsp_mask = df_uzio_id_str == detected_dsp_id
                        
                        if dsp_mask.any():
                            # Override position
                            df_uzio.loc[dsp_mask, 'Job Title'] = 'DSP Owner'
                            
                            # Shift to the top
                            dsp_rows = df_uzio[dsp_mask]
                            other_rows = df_uzio[~dsp_mask]
                            df_uzio = pd.concat([dsp_rows, other_rows], ignore_index=True)
                
                # Validate Uzio Data
                from utils.audit_utils import validate_uzio_data
                df_errors = validate_uzio_data(df_uzio)
                
                if not df_errors.empty:
                    st.warning("Some mandatory fields are blank or missing in the generated census. Please download the Validation Errors report.")
                    err_out = io.BytesIO()
                    df_errors.to_csv(err_out, index=False)
                    err_out.seek(0)
                    
                    st.download_button(
                        label="Download Validation Errors (CSV)",
                        data=err_out.getvalue(),
                        file_name=f"Validation_Errors_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )
                
                # Inject into the Master Template
                from utils.audit_utils import inject_into_uzio_template
                wb = inject_into_uzio_template(df_uzio, template_path="templates/Uzio_Census_Template.xlsm")
                
                # Write to buffer
                out = io.BytesIO()
                wb.save(out)
                out.seek(0)
                    
                st.success("Uzio Template Generated Successfully!")
                timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M')
                st.download_button(
                    label="Download Uzio Template",
                    data=out.getvalue(),
                    file_name=f"Uzio_Census_Template_Paycom_{timestamp}.xlsm",
                    mime="application/vnd.ms-excel.sheet.macroEnabled.12"
                )
            except Exception as e:
                st.error(f"Error generating template: {e}")
