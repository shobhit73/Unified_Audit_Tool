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
        has_soft_warnings = paycom_pos_fixes or not flsa_corrections.empty or not flsa_blanks.empty or not intern_corrections.empty or not email_fallbacks.empty
        if has_soft_warnings:
            with st.expander("System Auto-Corrections & Minor Warnings", expanded=False):
                if paycom_pos_fixes:
                    st.markdown(f"- ℹ️ **Position Auto-Fill:** {len(paycom_pos_fixes)} employee(s) had a blank Position, but it was automatically filled using their Department Description.")
                if not flsa_corrections.empty:
                    st.markdown(f"- ℹ️ **FLSA Auto-Corrections:** {len(flsa_corrections)} employee(s) had mismatched FLSA classifications. These have been auto-corrected.")
                if not flsa_blanks.empty:
                    st.markdown(f"- ⚠️ **Blank FLSA Classification:** {len(flsa_blanks)} employee(s) have a Pay Type set but FLSA Classification is blank.")
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

        set_dsp_owner = False
        if detected_dsp_id:
            name_disp = f" ({detected_dsp_name})" if detected_dsp_name else ""
            st.info(f"**DSP Owner Detected:** Employee **{detected_dsp_id}**{name_disp} supervises the most employees.")
            set_dsp_owner = st.checkbox(
                f"Automatically set Position to **'DSP Owner'** for Employee {detected_dsp_id} and move them to the **very top** of all generated files.",
                value=True, key="pc_set_dsp_owner"
            )

        # --- AUTO-FIX OPTIONS (always shown, checkbox-based) ---
        from utils.preprocess_source_data import detect_fixable_issues, apply_auto_fixes
        fixable = detect_fixable_issues(df_paycom, resolved_field_map)

        has_any_fixable = (fixable['flsa_blank_count'] > 0 or fixable['email_blank_count'] > 0 
                           or fixable['zip_fixable_count'] > 0 or fixable['hours_blank_count'] > 0
                           or fixable.get('inactive_status_count', 0) > 0
                           or fixable.get('temporary_status_count', 0) > 0
                           or fixable.get('blank_dol_active_count', 0) > 0
                           or fixable.get('blank_dol_term_count', 0) > 0
                           or fixable.get('invalid_date_count', 0) > 0)

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
            if fixable.get('inactive_status_count', 0) > 0:
                fix_inactive = st.checkbox(
                    f"**Fix 'Inactive' Employee Status** — Change to 'Terminated' ({fixable['inactive_status_count']} employee(s) affected)",
                    value=True, key="pc_fix_inactive"
                )
            if fixable.get('temporary_status_count', 0) > 0:
                fix_temporary = st.checkbox(
                    f"**Fix 'Temporary' Employee Status** — Change to 'Seasonal' ({fixable['temporary_status_count']} employee(s) affected)",
                    value=True, key="pc_fix_temporary"
                )
            if fixable.get('blank_dol_active_count', 0) > 0:
                fix_blank_dol_active = st.checkbox(
                    f"**Fix Blank 'DOL_Status'** — Set to 'Full-Time' for Active employees ({fixable['blank_dol_active_count']} employee(s) affected)",
                    value=True, key="pc_fix_blank_dol_active"
                )
            if fixable.get('blank_dol_term_count', 0) > 0:
                fix_blank_dol_term = st.checkbox(
                    f"**Fix Blank 'DOL_Status'** — Delete Row for Terminated employees ({fixable['blank_dol_term_count']} employee(s) affected)",
                    value=True, key="pc_fix_blank_dol_term"
                )
            if fixable.get('invalid_date_count', 0) > 0:
                fix_invalid_dates = st.checkbox(
                    f"**Fix Invalid Dates** — Blank out '00/00/0000' values ({fixable['invalid_date_count']} instance(s) affected)",
                    value=True, key="pc_fix_invalid_dates"
                )
            if fixable.get('type_blank_count', 0) > 0:
                fix_type_blanks = st.checkbox(
                    f"**Fix Blank Worker Category (Employment Type)** — Set to 'Part Time' ({fixable['type_blank_count']} employee(s) affected)",
                    value=True, key="pc_fix_type_blanks"
                )

        st.markdown("---")
        
        fixes_to_apply = {
            'fix_flsa': fix_flsa if 'fix_flsa' in locals() else False,
            'fix_email': fix_email if 'fix_email' in locals() else False,
            'fix_zip': fix_zip if 'fix_zip' in locals() else False,
            'fix_hours': fix_hours if 'fix_hours' in locals() else False,
            'fix_inactive': fix_inactive if 'fix_inactive' in locals() else False,
            'fix_temporary': fix_temporary if 'fix_temporary' in locals() else False,
            'fix_blank_dol_active': fix_blank_dol_active if 'fix_blank_dol_active' in locals() else False,
            'fix_blank_dol_term': fix_blank_dol_term if 'fix_blank_dol_term' in locals() else False,
            'fix_invalid_dates': fix_invalid_dates if 'fix_invalid_dates' in locals() else False,
            'fix_type_blanks': fix_type_blanks if 'fix_type_blanks' in locals() else False,
        }
        
        if any(fixes_to_apply.values()):
            fixes = apply_auto_fixes(df_paycom, resolved_field_map, fixes_to_apply)
            
            # Display what was fixed
            fix_count = 0
            success_messages = []
            
            if not fixes['flsa_fills'].empty:
                fix_count += len(fixes['flsa_fills'])
                success_messages.append(f"- **FLSA Auto-Fill:** {len(fixes['flsa_fills'])} employee(s)")
            
            if not fixes['email_fallbacks'].empty:
                fix_count += len(fixes['email_fallbacks'])
                success_messages.append(f"- **Email Fallback:** {len(fixes['email_fallbacks'])} employee(s)")
            
            if not fixes['zip_corrections'].empty:
                fix_count += len(fixes['zip_corrections'])
                success_messages.append(f"- **Zip Code Corrections:** {len(fixes['zip_corrections'])} employee(s)")
            
            if not fixes['hours_fixes'].empty:
                fix_count += len(fixes['hours_fixes'])
                success_messages.append(f"- **Working Hours Fix:** {len(fixes['hours_fixes'])} employee(s)")
                
            if 'inactive_fixes' in fixes and not fixes['inactive_fixes'].empty:
                fix_count += len(fixes['inactive_fixes'])
                success_messages.append(f"- **Inactive Status Fix:** {len(fixes['inactive_fixes'])} employee(s)")
                
            if 'temporary_fixes' in fixes and not fixes['temporary_fixes'].empty:
                fix_count += len(fixes['temporary_fixes'])
                success_messages.append(f"- **Temporary Status Fix:** {len(fixes['temporary_fixes'])} employee(s)")
                
            if 'dol_active_fixes' in fixes and not fixes['dol_active_fixes'].empty:
                fix_count += len(fixes['dol_active_fixes'])
                success_messages.append(f"- **Blank DOL Fix (Active):** {len(fixes['dol_active_fixes'])} employee(s)")
                
            if 'dol_term_fixes' in fixes and not fixes['dol_term_fixes'].empty:
                fix_count += len(fixes['dol_term_fixes'])
                success_messages.append(f"- **Blank DOL Fix (Terminated):** {len(fixes['dol_term_fixes'])} employee(s) deleted")
                
            if 'invalid_date_fixes' in fixes and not fixes['invalid_date_fixes'].empty:
                fix_count += len(fixes['invalid_date_fixes'])
                success_messages.append(f"- **Invalid Dates Blanked:** {len(fixes['invalid_date_fixes'])} dates corrected")
                
            if 'type_blank_fixes' in fixes and not fixes['type_blank_fixes'].empty:
                fix_count += len(fixes['type_blank_fixes'])
                success_messages.append(f"- **Worker Category Auto-Fill:** {len(fixes['type_blank_fixes'])} employee(s) set to Part Time")
            
            if fix_count > 0:
                msg = f"✅ **{fix_count} total fix(es) actively applied to the data!**\n\n" + "\n".join(success_messages)
                st.success(msg)
                
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
        
        # Also move DSP owner to the top if requested
        if set_dsp_owner and detected_dsp_id:
            emp_id_col = resolved_field_map.get('Employee ID')
            if emp_id_col and emp_id_col in df_download.columns:
                df_dl_id_str = df_download[emp_id_col].astype(str).str.strip()
                dsp_mask = df_dl_id_str == detected_dsp_id
                if dsp_mask.any():
                    # Try setting Job Title/Position here too if mapped
                    p_col = resolved_field_map.get('Job Title')
                    if p_col and p_col in df_download.columns:
                        df_download.loc[dsp_mask, p_col] = 'DSP Owner'
                    dsp_rows = df_download[dsp_mask]
                    other_rows = df_download[~dsp_mask]
                    df_download = pd.concat([dsp_rows, other_rows], ignore_index=True)

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

        st.markdown("---")
        st.markdown("### Step 3: Finalize & Generate")

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
                    import traceback
                    error_traceback = traceback.format_exc()
                    st.error(f"**Error generating template:** {e}")
                    with st.expander("View Detailed Error Log (Traceback)", expanded=False):
                        st.code(error_traceback, language="python")
