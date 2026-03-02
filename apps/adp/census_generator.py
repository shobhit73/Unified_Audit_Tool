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
    'Working Hours': ['Regular Hours', 'Standard Hours'],
    'Job Title': ['Job Title Description', 'Job Title'],
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
    'Zip': ['Legal / Preferred Address: Zip / Postal Code', 'Zip Code'],
    'State': ['Primary Address: State / Territory Code', 'State'],
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
    2. Click **Generate Uzio Template**.
    3. Download the correctly formatted Uzio `.xlsx` file.
    """)
    
    adp_file = st.file_uploader("Upload ADP Census Export", type=["xlsx", "csv"], key="adp_gen_upload")
    
    if adp_file:
        if st.button("Generate Uzio Template", type="primary"):
            with st.spinner("Processing..."):
                try:
                    if adp_file.name.lower().endswith('.csv'):
                        df_adp = pd.read_csv(adp_file, dtype=str)
                    else:
                        df_adp = pd.read_excel(adp_file, dtype=str)
                        
                    # Normalize source columns
                    df_adp.columns = [norm_colname(c) for c in df_adp.columns]
                    
                    # Normalize and Resolve the VENDOR_FIELD_MAP values
                    # We pick the first column name in the fallback list that actually exists in df_adp
                    resolved_field_map = {}
                    for std_name, vendor_cols in ADP_FIELD_MAP.items():
                        found = False
                        for vc in vendor_cols:
                            norm_vc = norm_colname(vc)
                            if norm_vc in df_adp.columns:
                                resolved_field_map[std_name] = norm_vc
                                found = True
                                break
                        # If none found, just map to the first one so it defaults to blank downstream
                        if not found:
                            resolved_field_map[std_name] = norm_colname(vendor_cols[0])
                    
                    
                    # --- INTERACTIVE UI MAPPING ---
                    st.markdown("### Step 2: Map Data to Uzio Format")
                    st.markdown("Please map the unique Job Titles and Work Locations found in your source file to the acceptable Uzio formats.")
                    
                    src_job_col = resolved_field_map.get('Job Title')
                    src_loc_col = resolved_field_map.get('Work Location')
                    
                    # Extract unique Jobs
                    unique_jobs = []
                    if src_job_col and src_job_col in df_adp.columns:
                        unique_jobs = sorted([j for j in df_adp[src_job_col].dropna().unique() if str(j).strip()])
                        
                    # Extract unique Locations
                    unique_locs = []
                    if src_loc_col and src_loc_col in df_adp.columns:
                        unique_locs = sorted([l for l in df_adp[src_loc_col].dropna().unique() if str(l).strip()])
                        
                    # Create mapping dataframes for the editor
                    df_job_map = pd.DataFrame({"Source Job Title": unique_jobs, "Mapped Uzio Job Title": [None]*len(unique_jobs)})
                    df_loc_map = pd.DataFrame({"Source Work Location": unique_locs, "Mapped Uzio Work Location": [None]*len(unique_locs)})
                    
                    allowed_titles = [
                        'DSP Owner', 'Operations Manager', 'Operations Lead', 'Fleet Manager', 
                        'Safety Manager', 'Performance Manager', 'Trainer', 'Human Resources', 
                        'Recruiter', 'Office Personnel', 'Payroll Assistant', 'Finance', 
                        'Dispatch', 'Management', 'Admin', 'Survey', 'Warehouse', 'Walker', 
                        'Driver', 'Helper', 'Driver-Lite', 'Driver-Step Van', 
                        'Driver-Unscheduled', 'Lead Driver', 'DDU Dedicated', 'DDU Shared', 
                        'Non-DSP Related', 'Driver -Major Appliance'
                    ]

                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Job Title Mapping**")
                        edited_jobs = st.data_editor(
                            df_job_map, 
                            column_config={
                                "Source Job Title": st.column_config.Column(disabled=True),
                                "Mapped Uzio Job Title": st.column_config.SelectboxColumn("Select Uzio Role", options=allowed_titles, required=True)
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
                        st.warning("Please fill out all mappings in the tables above to enable Generation.")
                        st.stop()
                        
                    # Apply Job Title Mapping
                    if src_job_col and src_job_col in df_adp.columns:
                        job_dict = dict(zip(edited_jobs['Source Job Title'], edited_jobs['Mapped Uzio Job Title']))
                        df_uzio['Job Title'] = df_adp[src_job_col].map(job_dict).fillna(df_adp[src_job_col])
                        
                    # Apply Work Location Mapping
                    if src_loc_col and src_loc_col in df_adp.columns:
                        loc_dict = dict(zip(edited_locs['Source Work Location'], edited_locs['Mapped Uzio Work Location']))
                        df_uzio['Work Location'] = df_adp[src_loc_col].map(loc_dict).fillna(df_adp[src_loc_col])
                    
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
