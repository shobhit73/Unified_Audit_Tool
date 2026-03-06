# ADP Census Generator - v2.5 (with FLSA blank check, whitespace-safe mapping)
import io
import pandas as pd
import streamlit as st
from utils.audit_utils import generate_uzio_template

APP_TITLE = "ADP to Uzio Census Template Generator"

# Standard mapping: Internal Standard Name -> list of possible ADP Column Names (fallbacks)
ADP_FIELD_MAP = {
    'Employee ID': ['Associate ID', 'File Number', 'Employee ID'],
    'First Name': ['Legal First Name', 'First Name'],
    'Last Name': ['Legal Last Name', 'Last Name'],
    'Middle Initial': ['Legal Middle Name', 'Middle Name', 'Middle Initial'],
    'Employment Status': ['Position Status', 'Worker Status', 'Status'],
    'Employment Type': ['Worker Category Description', 'Worker Category', 'Employment Type'],
    'Hire Date': ['Hire/Rehire Date', 'Hire Date', 'Most Recent Hire Date'],
    'Original Hire Date': ['Hire Date', 'Original Hire Date'],
    'Termination Date': ['Termination Date'],
    'Termination Reason': ['Termination Reason Description', 'Termination Reason'],
    'Pay Type': ['Regular Pay Rate Description', 'Pay Type'],
    'Annual Salary': ['Annual Salary'],
    'Hourly Pay Rate': ['Regular Pay Rate Amount', 'Hourly Rate'],
    'Working Hours': ['Working Hours Per Week', 'Working Hours Per week', 'Regular Hours', 'Standard Hours'],
    'Job Title': ['Job Title Description', 'Job Title', 'Department Description'],
    'Department': ['Department Description', 'Department'],
    'Work Email': ['Work Contact: Work Email', 'Work Email'],
    'Personal Email': ['Personal Contact: Personal Email', 'Personal Email'],
    'Phone Number': ['Personal Contact: Personal Mobile', 'Primary Mobile', 'Mobile', 'Phone Number'],
    'SSN': ['Tax ID (SSN)', 'SSN'],
    'DOB': ['Birth Date', 'Date of Birth', 'DOB'],
    'Gender': ['Sex', 'Gender (Self-ID)', 'Gender'],
    'Tobacco User': ['Tobacco User'],
    'FLSA Classification': ['FLSA Description', 'FLSA Status'],
    'Address Line 1': ['Primary Address: Address Line 1', 'Address Line 1'],
    'Address Line 2': ['Primary Address: Address Line 2', 'Address Line 2'],
    'City': ['Primary Address: City', 'City'],
    'Zip': ['Primary Address: Zip / Postal Code', 'Legal / Preferred Address: Zip / Postal Code', 'Zip Code'],
    'State': ['Primary Address: State / Territory Code (Personal Profile)', 'Primary Address: State / Territory Code', 'State'],
    'Mailing Address Line 1': ['Legal / Preferred Address: Address Line 1'],
    'Mailing Address Line 2': ['Legal / Preferred Address: Address Line 2'],
    'Mailing City': ['Legal / Preferred Address: City'],
    'Mailing Zip': ['Legal / Preferred Address: Zip / Postal Code'],
    'Mailing State': ['Legal / Preferred Address: State / Territory Code'],
    'Reports To ID': ['Reports To Associate ID', 'Reports To'],
    'Protected Veteran Status': ['Protected Veteran Status'],
    'EEO Job Category': ['EEOC Job Classification'],
    'Ethnicity': ['Ethnicity'],
    'SOC Code': ['SOC Code'],
    'Work Location': ['Location', 'Location Description', 'Work Location']
}

ALLOWED_JOB_TITLES = [
    'DSP Owner', 'Operations Manager', 'Operations Lead', 'Fleet Manager', 
    'Safety Manager', 'Performance Manager', 'Trainer', 'Human Resources', 
    'Recruiter', 'Office Personnel', 'Payroll Assistant', 'Finance', 
    'Dispatch', 'Management', 'Admin', 'Survey', 'Warehouse', 'Walker', 
    'Driver', 'Helper', 'Driver-Lite', 'Driver-Step Van', 
    'Non-DSP Related', 'Driver -Major Appliance'
]

REQUIRED_ADP_COLUMNS = [
    'Legal First Name (Personal Profile)',
    'Legal Middle Name (Personal Profile)',
    'Legal Last Name (Personal Profile)',
    'Generation Suffix Code (Personal Profile)',
    'Generation Suffix Description (Personal Profile)',
    'Associate ID (Employment Profile)',
    'Position ID (Employment Profile)',
    'Birth Date (Personal Profile)',
    'Tax ID (SSN) (Personal Profile)',
    'Hire Date (Employment Profile)',
    'Hire/Rehire Date (Employment Profile)',
    'Termination Date (Employment Profile)',
    'Termination Reason Code (Employment Profile)',
    'Termination Reason Description (Employment Profile)',
    'Tobacco User (Personal Profile)',
    'Gender / Sex (Self-ID) (Personal Profile)',
    'Marital Status Code (Personal Profile)',
    'Marital Status Description (Personal Profile)',
    'FLSA Description (Employment Profile)',
    'FLSA Code (Employment Profile)',
    'Worker category description (Employment Profile)',
    'Annual Salary (Employment Profile - Pay Rates)',
    'Job Title Description (Employment Profile)',
    'Position Start Date (Employment Profile)',
    'Reports To Associate ID (Employment Profile)',
    'EEOC Job Classification (Employment Profile)',
    'Race Description (Personal Profile)',
    'Primary Address: Address Line 1 (Personal Profile)',
    'Primary Address: Address Line 2 (Personal Profile)',
    'Primary Address: Address Line 3 (Personal Profile)',
    'Primary Address: City (Personal Profile)',
    'Primary Address: Country Code (Personal Profile)',
    'Primary Address: Country (Personal Profile)',
    'Primary Address: County (Personal Profile)',
    'Primary Address: State / Territory Code (Personal Profile)',
    'Primary Address: State / Territory Description (Personal Profile)',
    'Personal Contact: Personal Email (Personal Profile)',
    'Protected Veteran Status (Statutory Compliance)',
    'Disabled Veteran (Statutory Compliance)',
    'Work Address: Address Line 1 (Personal Profile)',
    'Work Address: Address Line 2 (Personal Profile)',
    'Work Address: City (Personal Profile)',
    'Work Address: State / Territory Code (Personal Profile)',
    'Work Address: Zip / Postal Code (Personal Profile)',
    'Location Description (Employment Profile)',
    'SOC Code (Tax Withholdings)',
    'SOC Description (Tax Withholdings)',
    'Compensation Information',
    'Pay Frequency (Employment Profile - Pay Rates)',
    'Payroll Name (Personal Profile)',
    'Standard Hours (Employment Profile - Pay Rates)',
    '# of Dependents (Personal Profile)',
    'Work Contact: Work Email (Personal Profile)',
    'Regular Pay Rate Code (Employment Profile - Pay Rates)',
    'Regular Pay Rate Description (Employment Profile - Pay Rates)',
    'Regular Pay Rate',
    'Position Status (Employment Profile)',
    "NAICS Workers' Comp Code (Employment Profile)",
    "NAICS Workers' Comp Description (Employment Profile)",
    "NAICS Workers' Comp",
    'Legal / Preferred Address: Address Line 1 (Personal Profile)',
    'Legal / Preferred Address: Address Line 2 (Personal Profile)',
    'Legal / Preferred Address: City (Personal Profile)',
    'Legal / Preferred Address: Zip / Postal Code (Personal Profile)',
    'Legal / Preferred Address: State / Territory Code (Personal Profile)',
    'Pronouns (Personal Profile)',
    'T-Shirt size (Personal Profile)'
]

def norm_colname(c: str) -> str:
    import re
    if c is None: return ""
    c = str(c).replace("\n", " ").replace("\r", " ")
    c = c.replace("\u00A0", " ")
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "")
    c = c.strip('"').strip("'")
    return c.lower()

def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    **Instructions**:
    1. Upload your **ADP Census Export** (.xlsx or .csv).
    2. Map your **Job Titles** and **Work Locations** in the tables below.
    3. Click **Generate Uzio Template**.
    4. Download the correctly formatted Uzio `.xlsx` file.
    """)
    
    adp_file = st.file_uploader("Upload ADP Census Export", type=["xlsx", "csv"], key="adp_gen_upload")
    
    if not adp_file:
        return
    
    # --- STEP 1: Read and process the source file (runs on every rerun) ---
    try:
        if adp_file.name.lower().endswith('.csv'):
            df_adp = pd.read_csv(adp_file, dtype=str)
        else:
            df_adp = pd.read_excel(adp_file, dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return
        
    # Save original column headers before normalization
    original_columns = list(df_adp.columns)
    
    # Normalize source columns
    df_adp.columns = [norm_colname(c) for c in df_adp.columns]
    
    # Build mapping: normalized -> original (for restoring headers on download)
    norm_to_orig = dict(zip(df_adp.columns, original_columns))
    
    # --- CHECK: Required mandatory columns ---
    missing_required = []
    adp_cols_normalized = set(df_adp.columns)
    
    for req_col in REQUIRED_ADP_COLUMNS:
        req_norm = norm_colname(req_col)
        if req_norm not in adp_cols_normalized:
            missing_required.append(req_col)
            
    if missing_required:
        st.error(f"**⛔ Halting Process: {len(missing_required)} Mandatory Column(s) Missing!**")
        st.markdown("Your uploaded ADP file is missing the following required standard columns:")
        for mc in missing_required:
            st.markdown(f"- `{mc}`")
        st.info("Please correct your ADP reporting template to include these columns and upload the file again.")
        return
    
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
    
    # --- CHECK: Position column fallback to Department Description ---
    job_col = resolved_field_map.get('Job Title')
    dept_col_norm = norm_colname('Department Description')
    if job_col and job_col in df_adp.columns:
        blank_count = df_adp[job_col].isna().sum() + (df_adp[job_col].astype(str).str.strip() == '').sum()
        if blank_count > 0 and dept_col_norm in df_adp.columns:
            # Fill blanks from Department Description
            mask = df_adp[job_col].isna() | (df_adp[job_col].astype(str).str.strip() == '')
            df_adp.loc[mask, job_col] = df_adp.loc[mask, dept_col_norm]
            st.warning(f"**Position Fallback:** {int(blank_count)} employee(s) had blank Job Title (Position). Falling back to **Department Description** for these employees.")
    elif dept_col_norm in df_adp.columns:
        # Job Title column not found at all, use Department Description
        resolved_field_map['Job Title'] = dept_col_norm
        st.warning("**Position column not found.** Falling back to **Department Description** for Job Title mapping.")
    
    # --- CHECK: Working Hours column (soft flag instead of hard stop) ---
    hours_col = resolved_field_map.get('Working Hours')
    if not hours_col or hours_col not in df_adp.columns:
        st.warning("**⚠️ 'Working Hours Per Week' column not found** in the source file. You can use the Auto-Fix option below to add this column, or fix it manually.")
    
    # --- CHECK: State column must exist ---
    state_col = resolved_field_map.get('State')
    if not state_col or state_col not in df_adp.columns:
        st.error("**⛔ 'Primary Address: State / Territory Code' column not found in the source file!** This column is required for state validation.")
        return
    
    # --- CHECK: Zip column must exist ---
    zip_col = resolved_field_map.get('Zip')
    if not zip_col or zip_col not in df_adp.columns:
        st.error("**⛔ 'Primary Address: Zip / Postal Code' column not found in the source file!** This column is required for zip code validation.")
        return
    
    # --- CHECK: Reports To Associate ID column (soft flag) ---
    reports_col = resolved_field_map.get('Reports To ID')
    if not reports_col or reports_col not in df_adp.columns:
        st.warning("**Reports To Associate ID column not found** in the source file. This field will be blank in the output.")
    
    # --- PRE-GENERATION SANITY CHECKS ---
    from utils.audit_utils import validate_source_data
    validation = validate_source_data(df_adp, resolved_field_map)
    
    hard_errors = validation['hard_errors']
    flsa_corrections = validation['flsa_corrections']
    flsa_blanks = validation['flsa_blanks']
    intern_corrections = validation['intern_corrections']
    email_fallbacks = validation['email_fallbacks']
    
    # Show soft warnings first (non-blocking)
    has_soft_warnings = not flsa_corrections.empty or not flsa_blanks.empty or not intern_corrections.empty or not email_fallbacks.empty
    if has_soft_warnings:
        with st.expander("System Auto-Corrections & Minor Warnings", expanded=False):
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
            key="adp_hard_err_dl"
        )
    else:
        st.success("✅ Source data passed all sanity checks!")
    
    # --- AUTO-FIX OPTIONS (always shown, checkbox-based) ---
    from utils.preprocess_source_data import detect_fixable_issues, apply_auto_fixes
    fixable = detect_fixable_issues(df_adp, resolved_field_map)
    
    has_any_fixable = (fixable['flsa_blank_count'] > 0 or fixable['email_blank_count'] > 0 
                       or fixable['zip_fixable_count'] > 0 or fixable['hours_blank_count'] > 0
                       or fixable.get('inactive_status_count', 0) > 0
                       or fixable.get('temporary_status_count', 0) > 0
                       or fixable.get('blank_dol_active_count', 0) > 0
                       or fixable.get('blank_dol_term_count', 0) > 0
                       or fixable.get('invalid_date_count', 0) > 0
                       or fixable.get('type_blank_count', 0) > 0)
    
    if has_any_fixable:
        st.markdown("---")
        st.markdown("### 🔧 Auto-Fix Options")
        st.markdown("Select which issues you'd like the tool to fix automatically:")
        
        fix_flsa = False
        fix_email = False
        fix_zip = False
        fix_hours = False
        fix_inactive = False
        fix_temporary = False
        fix_blank_dol_active = False
        fix_blank_dol_term = False
        fix_invalid_dates = False
        fix_type_blanks = False
        
        if fixable['flsa_blank_count'] > 0:
            fix_flsa = st.checkbox(
                f"**Fix Blank FLSA Classification** — Set based on Pay Type ({fixable['flsa_blank_count']} employee(s) affected)",
                value=True, key="adp_fix_flsa"
            )
        
        if fixable['email_blank_count'] > 0:
            fix_email = st.checkbox(
                f"**Fix Blank Work Email** — Use Personal Email as fallback ({fixable['email_blank_count']} employee(s) affected)",
                value=True, key="adp_fix_email"
            )
        
        if fixable['zip_fixable_count'] > 0:
            fix_zip = st.checkbox(
                f"**Fix Zip Code Issues** — Strip extra characters after dash or dot ({fixable['zip_fixable_count']} employee(s) affected)",
                value=True, key="adp_fix_zip"
            )
        
        if fixable['hours_blank_count'] > 0:
            label = f"**Fix Blank Working Hours** — Set to 0 ({fixable['hours_blank_count']} employee(s) affected)"
            if fixable['hours_col_missing']:
                label = f"**Fix Missing Working Hours Column** — Add column with 0 values ({fixable['hours_blank_count']} employee(s) affected)"
            fix_hours = st.checkbox(label, value=True, key="adp_fix_hours")
            
        if fixable.get('inactive_status_count', 0) > 0:
            fix_inactive = st.checkbox(
                f"**Fix 'Inactive' Employee Status** — Change to 'Terminated' ({fixable['inactive_status_count']} employee(s) affected)",
                value=True, key="adp_fix_inactive"
            )
        if fixable.get('temporary_status_count', 0) > 0:
            fix_temporary = st.checkbox(
                f"**Fix 'Temporary' Employee Status** — Change to 'Seasonal' ({fixable['temporary_status_count']} employee(s) affected)",
                value=True, key="adp_fix_temporary"
            )
        if fixable.get('blank_dol_active_count', 0) > 0:
            fix_blank_dol_active = st.checkbox(
                f"**Fix Blank 'DOL_Status'** — Set to 'Full-Time' for Active employees ({fixable['blank_dol_active_count']} employee(s) affected)",
                value=True, key="adp_fix_blank_dol_active"
            )
        if fixable.get('blank_dol_term_count', 0) > 0:
            fix_blank_dol_term = st.checkbox(
                f"**Fix Blank 'DOL_Status'** — Delete Row for Terminated employees ({fixable['blank_dol_term_count']} employee(s) affected)",
                value=True, key="adp_fix_blank_dol_term"
            )
        if fixable.get('invalid_date_count', 0) > 0:
            fix_invalid_dates = st.checkbox(
                f"**Fix Invalid Dates** — Blank out '00/00/0000' values ({fixable['invalid_date_count']} instance(s) affected)",
                value=True, key="adp_fix_invalid_dates"
            )
        if fixable.get('type_blank_count', 0) > 0:
            fix_type_blanks = st.checkbox(
                f"**Fix Blank Worker Category (Employment Type)** — Set to 'Part Time' ({fixable['type_blank_count']} employee(s) affected)",
                value=True, key="adp_fix_type_blanks"
            )

        st.markdown("---")
        
        fixes_to_apply = {
            'fix_flsa': fix_flsa,
            'fix_email': fix_email,
            'fix_zip': fix_zip,
            'fix_hours': fix_hours,
            'fix_inactive': fix_inactive,
            'fix_temporary': fix_temporary,
            'fix_blank_dol_active': fix_blank_dol_active,
            'fix_blank_dol_term': fix_blank_dol_term,
            'fix_invalid_dates': fix_invalid_dates,
            'fix_type_blanks': fix_type_blanks
        }
        
        if any(fixes_to_apply.values()):
            fixes = apply_auto_fixes(df_adp, resolved_field_map, fixes_to_apply)
            
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
                
        # --- DSP OWNER DETECTION (ADP) ---
        col_sup_code = resolved_field_map.get('Reports To ID')
        if not col_sup_code or col_sup_code not in df_adp.columns:
            # Maybe it wasn't mapped, try to find 'Reports To Associate ID' directly as a fallback
            if 'Reports To Associate ID' in df_adp.columns:
                col_sup_code = 'Reports To Associate ID'

        detected_dsp_id = None
        detected_dsp_name = ""
        
        if col_sup_code and col_sup_code in df_adp.columns:
            # Filter out blanks
            valid_sups = df_adp[df_adp[col_sup_code].notna() & (df_adp[col_sup_code].astype(str).str.strip() != "")]
            if not valid_sups.empty:
                sup_counts = valid_sups[col_sup_code].value_counts()
                if not sup_counts.empty:
                    detected_dsp_id = str(sup_counts.index[0]).strip()
                    
                    # Try to get their name
                    emp_code_col = resolved_field_map.get('Employee ID')
                    if emp_code_col and emp_code_col in df_adp.columns:
                        match = df_adp[df_adp[emp_code_col].astype(str).str.strip() == detected_dsp_id]
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
                f"Automatically set Job Title to **'DSP Owner'** for Employee {detected_dsp_id} and move them to the **very top** of all generated files.",
                value=True, key="adp_set_dsp_owner"
            )

        # --- Optional Location Mapping (in Tab 1) ---
        src_loc_col_af = resolved_field_map.get('Work Location')
        unique_locs_af = []
        if src_loc_col_af and src_loc_col_af in df_adp.columns:
            unique_locs_af = sorted([str(l).strip() for l in df_adp[src_loc_col_af].dropna().unique() if str(l).strip()])

        fix_loc_mapping = False
        edited_locs_af = None

        if unique_locs_af:
            st.markdown("---")
            fix_loc_mapping = st.checkbox(
                f"**Map Work Locations (Optional)** — Map {len(unique_locs_af)} unique Work Location(s) directly in the source data",
                value=False, key="adp_fix_locs"
            )

        if fix_loc_mapping:
            df_loc_map_af = pd.DataFrame({"Source Work Location": unique_locs_af, "Mapped Work Location": pd.Series([""]*len(unique_locs_af), dtype=str)})
            edited_locs_af = st.data_editor(
                df_loc_map_af,
                column_config={
                    "Source Work Location": st.column_config.Column(disabled=True),
                    "Mapped Work Location": st.column_config.TextColumn("Enter Standardized Location", required=True)
                },
                hide_index=True, use_container_width=True, key="adp_af_loc_editor"
            )
            
            # Immediately apply this mapping to df_adp so the download includes it
            if edited_locs_af is not None and not edited_locs_af.empty:
                # Only applying mappings that are actually filled out
                valid_maps = edited_locs_af[edited_locs_af['Mapped Work Location'].str.strip() != ""]
                if not valid_maps.empty:
                    loc_dict_af = dict(zip(valid_maps['Source Work Location'], valid_maps['Mapped Work Location']))
                    stripped_locs = df_adp[src_loc_col_af].astype(str).str.strip()
                    df_adp[src_loc_col_af] = stripped_locs.map(loc_dict_af).fillna(df_adp[src_loc_col_af])
                    st.success(f"**Work Location Mapping:** Applied mapping for {len(loc_dict_af)} unique location(s).")
                
        # --- Download Corrected Source ---
        st.markdown("### 📥 Download Cleaned Source Data")
        st.markdown("You can download the partially cleaned source file containing all the fixes applied above.")
        
        df_download = df_adp.copy()
        
        # Move DSP owner to the top if requested
        if set_dsp_owner and detected_dsp_id:
            emp_id_col = resolved_field_map.get('Employee ID')
            if emp_id_col and emp_id_col in df_download.columns:
                df_dl_id_str = df_download[emp_id_col].astype(str).str.strip()
                dsp_mask = df_dl_id_str == detected_dsp_id
                if dsp_mask.any():
                    # Set Job Title Definition for DSP Owner
                    j_col = resolved_field_map.get('Job Title')
                    if j_col and j_col in df_download.columns:
                        df_download.loc[dsp_mask, j_col] = 'DSP Owner'
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
                file_name=f"ADP_Cleaned_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                key="adp_corrected_csv_dl"
            )
        with dl_col2:
            corrected_xlsx = io.BytesIO()
            df_download.to_excel(corrected_xlsx, index=False, engine='openpyxl')
            corrected_xlsx.seek(0)
            st.download_button(
                label="📥 Download Corrected Source (XLSX)",
                data=corrected_xlsx.getvalue(),
                file_name=f"ADP_Cleaned_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="adp_corrected_xlsx_dl"
            )
    
    # --- STEP 2: Interactive UI Mapping (persists across reruns) ---
    st.markdown("---")
    st.markdown("### Step 2: Map Data to Uzio Format")
    st.markdown("Please map the unique Job Titles and Work Locations found in your source file to the acceptable Uzio formats.")
    
    src_job_col = resolved_field_map.get('Job Title')
    src_loc_col = resolved_field_map.get('Work Location')
    
    # Extract unique Jobs
    unique_jobs = []
    if src_job_col and src_job_col in df_adp.columns:
        unique_jobs = sorted([str(j).strip() for j in df_adp[src_job_col].dropna().unique() if str(j).strip()])
        
    # Extract unique Locations
    unique_locs = []
    if src_loc_col and src_loc_col in df_adp.columns:
        unique_locs = sorted([str(l).strip() for l in df_adp[src_loc_col].dropna().unique() if str(l).strip()])
        
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
            key="adp_job_editor"
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
            key="adp_loc_editor"
        )
    
    # Check if mapping is completely filled out
    job_map_complete = not edited_jobs['Mapped Uzio Job Title'].isna().any() if not edited_jobs.empty else True
    loc_map_complete = not edited_locs['Mapped Uzio Work Location'].isna().any() and not (edited_locs['Mapped Uzio Work Location'] == "").any() if not edited_locs.empty else True
    
    if not job_map_complete or not loc_map_complete:
        st.warning("Please fill out all mappings in the tables above before generating the template.")
        return
    
    # --- STEP 3: Generate Template (only on button click) ---
    st.markdown("---")
    if st.button("Generate Uzio Template", type="primary", key="adp_gen_btn"):
        with st.spinner("Generating..."):
            try:
                # Generate Uzio Template
                df_uzio = generate_uzio_template(df_adp, resolved_field_map)
                
                # Apply Job Title Mapping
                if src_job_col and src_job_col in df_adp.columns:
                    job_dict = dict(zip(edited_jobs['Source Job Title'], edited_jobs['Mapped Uzio Job Title']))
                    stripped_jobs = df_adp[src_job_col].astype(str).str.strip()
                    df_uzio['Job Title'] = stripped_jobs.map(job_dict).fillna(df_adp[src_job_col])
                    
                # Apply Work Location Mapping
                if src_loc_col and src_loc_col in df_adp.columns:
                    loc_dict = dict(zip(edited_locs['Source Work Location'], edited_locs['Mapped Uzio Work Location']))
                    stripped_locs = df_adp[src_loc_col].astype(str).str.strip()
                    df_uzio['Work Location'] = stripped_locs.map(loc_dict).fillna(df_adp[src_loc_col])
                    
                # Setup DSP Owner at the top of the Uzio sheet
                if set_dsp_owner and detected_dsp_id:
                    # 'Employee ID' is Uzio column Name
                    df_dl_id_str = df_uzio['Employee ID'].astype(str).str.strip()
                    dsp_mask = df_dl_id_str == detected_dsp_id
                    if dsp_mask.any():
                        df_uzio.loc[dsp_mask, 'Job Title'] = 'DSP Owner'
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
                    file_name=f"Uzio_Census_Template_ADP_{timestamp}.xlsm",
                    mime="application/vnd.ms-excel.sheet.macroEnabled.12"
                )
            except Exception as e:
                st.error(f"Error generating template: {e}")
