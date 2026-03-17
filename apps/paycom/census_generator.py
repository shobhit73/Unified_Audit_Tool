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
    'Original Hire Date': ['Original_Hire_Date', 'Hire Date', 'Original Hire Date'],
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
    # Remove bracketed suffixes like (Personal Profile) or (Employment Profile - Pay Rates)
    c = re.sub(r'\(.*?\)', '', c)
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
            
    tab_sanity, tab_gen = st.tabs(['🩺 Sanity Check & Auto-Fix', '⚙️ Uzio Template Generator'])
    with tab_sanity:
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

            fname = ""
            lname = ""
            if col_fname:
                val = row.get(col_fname)
                fname = str(val).strip() if pd.notna(val) else ""
            if col_lname:
                val = row.get(col_lname)
                lname = str(val).strip() if pd.notna(val) else ""
            emp_name = f"{fname} {lname}".strip()

            custom_missing = []

            # 1. DOL_Status blank check
            if col_dol:
                val_dol = row.get(col_dol)
                if pd.isna(val_dol) or str(val_dol).strip() == "":
                    emp_stat_str = str(row.get(col_emp_status)).strip().lower() if col_emp_status else ""
                    if "term" in emp_stat_str:
                        custom_missing.append("DOL_Status is blank for Terminated employee (Use Auto-Fix to delete row)")
                    else:
                        custom_missing.append("DOL_Status is blank for Active employee (Use Auto-Fix to set to 'Full-Time')")

            # 2. Employee Status blank check & "Inactive" / "Temporary" check
            if col_emp_status:
                val_emp = row.get(col_emp_status)
                if pd.isna(val_emp) or str(val_emp).strip() == "":
                    custom_missing.append("Employee Status is blank")
                elif str(val_emp).strip().lower() == "inactive":
                    custom_missing.append("Employee Status is 'Inactive' (Use Auto-Fix to set to 'Terminated')")
                elif str(val_emp).strip().lower() == "temporary":
                    custom_missing.append("Employee Status is 'Temporary' (Use Auto-Fix to set to 'Seasonal')")

            # 3. Position and Department Desc check
            if col_pos:
                val_pos = row.get(col_pos)
                if pd.isna(val_pos) or str(val_pos).strip() == "":
                    custom_missing.append("Position is blank")
                        
            # 4. Emergency Contact Spanish Characters Check
            # Look for emergency contact name columns
            emg_cols = [c for c in df_paycom.columns if 'emergency' in c and ('name' in c or 'contact' in c)]
            for ec in emg_cols:
                val_ec = row.get(ec)
                if pd.notna(val_ec) and str(val_ec).strip():
                    # Regex to find non-ASCII characters (often Spanish characters like á, é, í, ó, ú, ñ)
                    import re
                    if re.search(r'[^\x00-\x7F]', str(val_ec)):
                        custom_missing.append(f"Special/Spanish character found in {norm_to_orig.get(ec, ec)}: '{str(val_ec)}'. Please correct it.")

            if custom_missing:
                paycom_custom_errors.append({
                    'Employee ID': emp_ref,
                    'Name': emp_name,
                    'Issue': ", ".join(custom_missing)
                })

        # --- CHECK: State column must exist (Non-Blocking) ---
        state_col = resolved_field_map.get('State')
        if not state_col or state_col not in df_paycom.columns:
            st.warning("⚠️ **'Primary_State/Province' (or similar State) column not found!** State validation will be skipped.")

        # --- CHECK: Zip column must exist (Non-Blocking) ---
        zip_col = resolved_field_map.get('Zip')
        if not zip_col or zip_col not in df_paycom.columns:
            st.warning("⚠️ **'Primary_Zip/Postal_Code' (or similar Zip) column not found!** Zip code validation will be skipped.")

        # --- PRE-GENERATION SANITY CHECKS ---
        from utils.audit_utils import validate_source_data
        validation = validate_source_data(df_paycom, resolved_field_map)

        flsa_corrections = validation['flsa_corrections']
        flsa_blanks = validation['flsa_blanks']
        intern_corrections = validation['intern_corrections']
        email_fallbacks = validation['email_fallbacks']
        salaried_drivers = validation.get('salaried_drivers', pd.DataFrame())
        anomalies = validation.get('anomalies', pd.DataFrame())

        # Merge custom Paycom hard errors with generic hard errors
        hard_errors_df = validation['hard_errors']
        if paycom_custom_errors:
            df_custom = pd.DataFrame(paycom_custom_errors)
            if not hard_errors_df.empty:
                # Merge and keep Name if possible
                hard_errors = pd.concat([hard_errors_df, df_custom]).groupby(['Employee ID', 'Name'])['Issue'].apply(lambda x: ', '.join(x)).reset_index()
            else:
                hard_errors = df_custom
        else:
            hard_errors = hard_errors_df

        # Show soft warnings first (non-blocking)
        has_soft_warnings = paycom_pos_fixes or not flsa_corrections.empty or not flsa_blanks.empty or not intern_corrections.empty or not email_fallbacks.empty or not anomalies.empty
        if has_soft_warnings:
            with st.expander("System Minor Warnings", expanded=False):
                if paycom_pos_fixes:
                    st.markdown(f"- ℹ️ **Position Auto-Fill:** {len(paycom_pos_fixes)} employee(s) had a blank Position, but it was automatically filled using their Department Description.")
                if not flsa_corrections.empty:
                    st.markdown(f"- ℹ️ **FLSA Auto-Corrections:** {len(flsa_corrections)} employee(s) had mismatched FLSA classifications. These have been auto-corrected.")
                if not flsa_blanks.empty:
                    st.markdown(f"- ⚠️ **Blank FLSA Classification:** {len(flsa_blanks)} employee(s) have a Pay Type set but FLSA Classification is blank.")
                if not anomalies.empty:
                    st.markdown(f"- ⚠️ **FLSA Anomalies:** {len(anomalies)} employee(s) have Hourly Exempt or Salaried Non-Exempt mismatches.")
                if not intern_corrections.empty:
                    st.markdown(f"- ⚠️ **Intern → Part Time:** {len(intern_corrections)} employee(s) had 'Intern' as Worker Category. Changed to **Part Time**.")
                if not email_fallbacks.empty:
                    st.markdown(f"- ℹ️ **Email Fallback:** {len(email_fallbacks)} employee(s) had blank Work Email. Personal Email was used instead.")

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

            err_xlsx = io.BytesIO()
            with pd.ExcelWriter(err_xlsx, engine='openpyxl') as writer:
                hard_errors.to_excel(writer, sheet_name="Critical Errors", index=False)
                if not anomalies.empty:
                    anomalies.to_excel(writer, sheet_name="FLSA Anomalies", index=False)
                if not salaried_drivers.empty:
                    salaried_drivers.to_excel(writer, sheet_name="Salaried Driver Exceptions", index=False)
            err_xlsx.seek(0)
            st.download_button(
                label="Download Error Report (XLSX)",
                data=err_xlsx.getvalue(),
                file_name=f"Source_Validation_Errors_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="pc_hard_err_dl"
            )
        else:
            st.success("✅ Source data passed all sanity checks!")
            


        # --- MANAGER DETECTION (PAYCOM) ---
        col_sup_code = None
        for cand in ['supervisor_primary_code', 'supervisor primary code', 'supervisorcode']:
            if cand in df_paycom.columns:
                col_sup_code = cand
                break
    
        top_manager_id = None
        top_manager_name = ""
        has_managers = False
    
        if col_sup_code:
            # Filter out blanks
            valid_sups = df_paycom[df_paycom[col_sup_code].notna() & (df_paycom[col_sup_code].astype(str).str.strip() != "")]
            if not valid_sups.empty:
                has_managers = True
                sup_counts = valid_sups[col_sup_code].value_counts()
                if not sup_counts.empty:
                    top_manager_id = str(sup_counts.index[0]).strip()
    
                    # Try to get their name
                    emp_code_col = resolved_field_map.get('Employee ID')
                    if emp_code_col and emp_code_col in df_paycom.columns:
                        match = df_paycom[df_paycom[emp_code_col].astype(str).str.strip() == top_manager_id]
                        if not match.empty:
                            fn = match.iloc[0].get(resolved_field_map.get('First Name'), '')
                            ln = match.iloc[0].get(resolved_field_map.get('Last Name'), '')
                            if pd.notna(fn) and pd.notna(ln):
                                top_manager_name = f"{str(fn).strip()} {str(ln).strip()}".strip()
    
        st.markdown("---")
    
        sort_by_manager = False
        if has_managers:
            if top_manager_id:
                name_disp = f" ({top_manager_name})" if top_manager_name else ""
                st.info(f"**Top Manager Detected:** Employee **{top_manager_id}**{name_disp} supervises the most employees.")
            
            sort_by_manager = st.checkbox(
                "Sort all reporting managers to the **very top** of all generated files (ordered by number of reportees).",
                value=True, key="paycom_sort_managers"
            )







        # --- Optional Location Mapping (in Tab 1) ---
        src_loc_col_af = resolved_field_map.get('Work Location')
        unique_locs_af = []
        if src_loc_col_af and src_loc_col_af in df_paycom.columns:
            unique_locs_af = sorted([str(l).strip() for l in df_paycom[src_loc_col_af].dropna().unique() if str(l).strip()])

        fix_loc_mapping = False
        edited_locs_af = None

        if unique_locs_af:
            st.markdown("---")
            fix_loc_mapping = st.checkbox(
                f"**Map Work Locations (Optional)** — Map {len(unique_locs_af)} unique Work Location(s) directly in the source data",
                value=False, key="pc_fix_locs"
            )

        if fix_loc_mapping:
            df_loc_map_af = pd.DataFrame({"Source Work Location": unique_locs_af, "Mapped Work Location": pd.Series([""]*len(unique_locs_af), dtype=str)})
            edited_locs_af = st.data_editor(
                df_loc_map_af,
                column_config={
                    "Source Work Location": st.column_config.Column(disabled=True),
                    "Mapped Work Location": st.column_config.TextColumn("Enter Standardized Location", required=True)
                },
                hide_index=True, use_container_width=True, key="pc_af_loc_editor"
            )
            
            # Immediately apply this mapping to df_paycom so the download includes it
            if edited_locs_af is not None and not edited_locs_af.empty:
                # Only applying mappings that are actually filled out
                valid_maps = edited_locs_af[edited_locs_af['Mapped Work Location'].str.strip() != ""]
                if not valid_maps.empty:
                    loc_dict_af = dict(zip(valid_maps['Source Work Location'], valid_maps['Mapped Work Location']))
                    stripped_locs = df_paycom[src_loc_col_af].astype(str).str.strip()
                    df_paycom[src_loc_col_af] = stripped_locs.map(loc_dict_af).fillna(df_paycom[src_loc_col_af])
                    st.success(f"**Work Location Mapping:** Applied mapping for {len(loc_dict_af)} unique location(s).")
                
        # --- Download Corrected Source ---
        st.markdown("### 📥 Download Cleaned Source Data")
        st.markdown("You can download the partially cleaned source file containing all the fixes applied above.")
        
        df_download = df_paycom.copy()
        
        # Sort by management hierarchy if requested
        if sort_by_manager and col_sup_code and col_sup_code in df_download.columns:
            emp_id_col = resolved_field_map.get('Employee ID')
            if emp_id_col and emp_id_col in df_download.columns:
                # Count reportees
                sup_counts = df_download[df_download[col_sup_code].notna() & (df_download[col_sup_code].astype(str).str.strip() != "")][col_sup_code].value_counts().to_dict()
                
                # Add temporary column for sorting
                df_download['__mgr_sort'] = df_download[emp_id_col].astype(str).str.strip().map(lambda x: sup_counts.get(x, 0))
                
                # Sort: Managers first (most reportees at top), then keeping original relative order
                df_download = df_download.sort_values(by='__mgr_sort', ascending=False, kind='stable').drop(columns=['__mgr_sort'])

        restored_cols = [norm_to_orig.get(c, c) for c in df_download.columns]
        df_download.columns = restored_cols
        
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            corrected_csv = io.BytesIO()
            df_download.to_csv(corrected_csv, index=False)
            corrected_csv.seek(0)
            st.download_button(
                label="📥 Download Corrected Source (CSV)",
                data=corrected_csv.getvalue(),
                file_name=f"Paycom_Cleaned_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
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
                file_name=f"Paycom_Cleaned_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="pc_corrected_xlsx_dl"
            )

        st.markdown("---")
    with tab_gen:
        # --- NEW: SELECTIVE UPDATE MODE TOGGLE (Moved inside tab for visibility) ---
        st.markdown("### Step 1: Generation Mode")
        gen_mode = st.radio(
            "Select how you want to generate the Uzio census:",
            ["Full Generation (New File from Scratch)", "Selective Column Update (Sync to Existing Template)"],
            index=0,
            help="Full Generation creates a fresh Uzio file. Selective Update modifies specific columns in an existing Uzio template.",
            key="pc_gen_mode_v2"
        )
        is_selective = ("Selective Column Update" in gen_mode)
        
        uzio_template_file = None
        selected_uzio_cols = []
        df_template = None
        job_seeds = {}
        loc_seeds = {}
        
        if is_selective:
            st.info("💡 **Mode: Selective Update**. We will update specific columns for employees in your source file into an existing Uzio template.")
            uzio_template_file = st.file_uploader("📤 Upload Pre-filled Uzio Template (.xlsm)", type=["xlsm"], key="pc_uzio_template_v2")
            
            if uzio_template_file:
                from utils.audit_utils import UZIO_RAW_MAPPING, read_uzio_raw_file, extract_mappings_from_uzio
                df_template = read_uzio_raw_file(uzio_template_file)
                
                if df_template is not None:
                    # Auto-fetch mappings
                    with st.spinner("Auto-fetching mappings from template..."):
                        job_seeds, loc_seeds = extract_mappings_from_uzio(df_paycom, df_template, resolved_field_map)
                        if job_seeds or loc_seeds:
                            st.success(f"✅ Auto-fetched {len(job_seeds)} Job Roles and {len(loc_seeds)} Work Locations from the template.")

                available_cols = list(UZIO_RAW_MAPPING.keys())
                selected_uzio_cols = st.multiselect(
                    "🎯 Select Uzio Columns to Sync/Update",
                    options=available_cols,
                    default=["Employee SSN"] if "Employee SSN" in available_cols else [],
                    help="Only these columns will be modified in the uploaded template.",
                    key="pc_sel_cols_v2" # Added unique key to prevent leakage
                )
                if not selected_uzio_cols:
                    st.warning("Please select at least one column to update.")

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
        # Seed with auto-fetched values
        job_map_list = [job_seeds.get(j) for j in unique_jobs]
        loc_map_list = [loc_seeds.get(l, "") for l in unique_locs]

        df_job_map = pd.DataFrame({
            "Source Job Title": unique_jobs, 
            "Mapped Uzio Job Title": pd.Series(job_map_list, dtype="object")
        })
        df_loc_map = pd.DataFrame({
            "Source Work Location": unique_locs, 
            "Mapped Uzio Work Location": pd.Series(loc_map_list, dtype=str)
        })

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

        st.markdown("---")
        st.markdown("### Step 3: Finalize & Generate")

        # --- STEP 4: Generate Template (only on button click) ---
        btn_label = "Update Uzio Template" if is_selective else "Generate Uzio Template"
        if st.button(btn_label, type="primary", key="pc_gen_btn"):
            if is_selective and not uzio_template_file:
                st.error("Please upload the Pre-filled Uzio Template first.")
                return
            if is_selective and not selected_uzio_cols:
                st.error("Please select at least one column to update.")
                return

            with st.spinner("Processing..."):
                try:
                    # 1. Prepare Mappings (Job Titles and Locations)
                    job_dict = {}
                    if src_job_col and src_job_col in df_paycom.columns:
                        job_dict = dict(zip(edited_jobs['Source Job Title'], edited_jobs['Mapped Uzio Job Title']))
                    
                    loc_dict = {}
                    if src_loc_col and src_loc_col in df_paycom.columns:
                        loc_dict = dict(zip(edited_locs['Source Work Location'], edited_locs['Mapped Uzio Work Location']))

                    # 2. Logic Branch: Full vs Selective
                    if is_selective:
                        from utils.audit_utils import read_uzio_template_df, selective_update_uzio
                        
                        # Read template
                        df_template = read_uzio_template_df(uzio_template_file)
                        if df_template is None:
                            st.error("Could not read Uzio template. Please ensure it's a valid .xlsm file with an 'Employee Details' sheet.")
                            return
                        
                        # Perform Merge
                        df_uzio, summary, df_changes = selective_update_uzio(df_paycom, df_template, selected_uzio_cols, resolved_field_map)
                        
                        st.info(summary)
                        if not df_changes.empty:
                            with st.expander("View Changes Preview", expanded=False):
                                st.dataframe(df_changes, hide_index=True, use_container_width=True)
                    else:
                        # Full Generation
                        df_uzio = generate_uzio_template(df_paycom, resolved_field_map)
                        
                        # Apply Job Title Mapping
                        if src_job_col and src_job_col in df_paycom.columns:
                            stripped_jobs = df_paycom[src_job_col].astype(str).str.strip()
                            df_uzio['Job Title'] = stripped_jobs.map(job_dict).fillna(df_paycom[src_job_col])
                        
                        # Apply Work Location Mapping
                        if src_loc_col and src_loc_col in df_paycom.columns:
                            stripped_locs = df_paycom[src_loc_col].astype(str).str.strip()
                            df_uzio['Work Location'] = stripped_locs.map(loc_dict).fillna(df_paycom[src_loc_col])

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

                    # Sort by management hierarchy for Uzio sheet if requested
                    if sort_by_manager:
                        # Find the Employee ID column in df_uzio (case-insensitive)
                        uzio_id_col = next(
                            (c for c in df_uzio.columns
                             if str(c).strip().lower().replace('_', ' ') == 'employee id' or str(c).strip().lower() == 'employee id*'),
                            None
                        )
                        # Find the Reports To ID column in Uzio template (mapped from Paycom col_sup_col)
                        uzio_sup_col = 'Reports To Associate ID' if 'Reports To Associate ID' in df_uzio.columns else 'Reports To ID'
                        
                        if uzio_id_col and uzio_id_col in df_uzio.columns and uzio_sup_col in df_uzio.columns:
                            # Count reportees using the IDs present in the Uzio dataset
                            sup_counts_uz = df_uzio[df_uzio[uzio_sup_col].notna() & (df_uzio[uzio_sup_col].astype(str).str.strip() != "")][uzio_sup_col].value_counts().to_dict()
                            
                            df_uzio['__mgr_sort_uz'] = df_uzio[uzio_id_col].astype(str).str.strip().map(lambda x: sup_counts_uz.get(x, 0))
                            df_uzio = df_uzio.sort_values(by='__mgr_sort_uz', ascending=False, kind='stable').drop(columns=['__mgr_sort_uz'])

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
                    if is_selective:
                        uzio_template_file.seek(0)
                        wb = inject_into_uzio_template(df_uzio, uzio_template_file)
                    else:
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
                    import traceback
                    error_traceback = traceback.format_exc()
                    st.error(f"**Error generating template:** {e}")
                    with st.expander("View Detailed Error Log (Traceback)", expanded=False):
                        st.code(error_traceback, language="python")
