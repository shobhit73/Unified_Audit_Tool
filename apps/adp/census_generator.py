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
    job_map_file = st.file_uploader("Upload Job Title Mapping (Optional)", type=["xlsx", "csv"], key="adp_gen_job_map")
    loc_map_file = st.file_uploader("Upload Work Location Mapping (Optional)", type=["xlsx", "csv"], key="adp_gen_loc_map")
    
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
                    
                    # Generate Uzio Template
                    df_uzio = generate_uzio_template(df_adp, resolved_field_map)
                    
                    # Apply Job Title Mapping
                    src_job_col = resolved_field_map.get('Job Title')
                    if src_job_col and src_job_col in df_adp.columns:
                        job_mapping = {}
                        if job_map_file:
                            try:
                                if job_map_file.name.lower().endswith('.csv'):
                                    df_map = pd.read_csv(job_map_file, dtype=str)
                                else:
                                    df_map = pd.read_excel(job_map_file, dtype=str)
                                
                                if len(df_map.columns) >= 2:
                                    for _, r in df_map.iterrows():
                                        src = str(r.iloc[0]).strip().lower()
                                        tgt = str(r.iloc[1]).strip()
                                        if src != 'nan' and src:
                                            job_mapping[src] = tgt if tgt != 'nan' else ""
                            except Exception as e:
                                st.warning(f"Could not read Job Title Mapping: {e}")
                                
                        def map_job(job_val):
                            if pd.isna(job_val): return ""
                            j = str(job_val).strip()
                            j_lower = j.lower()
                            if job_map_file and j_lower in job_mapping:
                                return job_mapping[j_lower]
                            return j
                            
                        df_uzio['Job Title'] = df_adp[src_job_col].apply(map_job)
                    
                    # Apply Work Location Mapping
                    src_loc_col = resolved_field_map.get('Work Location')
                    if src_loc_col and src_loc_col in df_adp.columns:
                        loc_mapping = {}
                        if loc_map_file:
                            try:
                                if loc_map_file.name.lower().endswith('.csv'):
                                    df_loc_map = pd.read_csv(loc_map_file, dtype=str)
                                else:
                                    df_loc_map = pd.read_excel(loc_map_file, dtype=str)
                                
                                if len(df_loc_map.columns) >= 2:
                                    for _, r in df_loc_map.iterrows():
                                        src = str(r.iloc[0]).strip().lower()
                                        tgt = str(r.iloc[1]).strip()
                                        if src != 'nan' and src:
                                            loc_mapping[src] = tgt if tgt != 'nan' else ""
                            except Exception as e:
                                st.warning(f"Could not read Work Location Mapping: {e}")
                                
                        def map_loc(loc_val):
                            if pd.isna(loc_val): return ""
                            l = str(loc_val).strip()
                            l_lower = l.lower()
                            if loc_map_file and l_lower in loc_mapping:
                                return loc_mapping[l_lower]
                            return l
                            
                        df_uzio['Work Location'] = df_adp[src_loc_col].apply(map_loc)
                    
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
