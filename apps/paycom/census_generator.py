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
        
    # Normalize source columns
    df_paycom.columns = [norm_colname(c) for c in df_paycom.columns]
    
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
    
    # --- PRE-GENERATION SANITY CHECKS ---
    from utils.audit_utils import validate_source_data
    validation = validate_source_data(df_paycom, resolved_field_map)
    
    hard_errors = validation['hard_errors']
    flsa_corrections = validation['flsa_corrections']
    flsa_blanks = validation['flsa_blanks']
    intern_corrections = validation['intern_corrections']
    email_fallbacks = validation['email_fallbacks']
    
    # Show soft warnings first (non-blocking)
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
                
                if fix_count > 0:
                    st.success(f"✅ {fix_count} fix(es) applied successfully!")
                    
                    # Provide corrected source file for download (CSV and XLSX)
                    st.markdown("**Download Corrected Source File:**")
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        corrected_csv = io.BytesIO()
                        df_paycom.to_csv(corrected_csv, index=False)
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
                        df_paycom.to_excel(corrected_xlsx, index=False, engine='openpyxl')
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
    
    # --- STEP 3: Generate Template (only on button click) ---
    st.markdown("---")
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
