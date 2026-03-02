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
    'Job Title': ['Position', 'Job Title'],
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
    'Work Location': ['Location', 'Work Location']
}

def norm_colname(c: str) -> str:
    import re
    if c is None: return ""
    c = str(c).replace("\n", " ").replace("\r", " ")
    c = c.replace("\u00A0", " ")
    c = c.replace("’", "'").replace("“", '"').replace("”", '"')
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "")
    c = c.strip('"').strip("'")
    return c.lower()

def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    **Instructions**:
    1. Upload your **Paycom Census Export** (.csv or .xlsx).
    2. Click **Generate Uzio Template**.
    3. Download the correctly formatted Uzio `.xlsx` file.
    """)
    
    paycom_file = st.file_uploader("Upload Paycom Census Export", type=["xlsx", "csv"], key="pc_gen_upload")
    job_map_file = st.file_uploader("Upload Job Title Mapping (Optional)", type=["xlsx", "csv"], key="pc_gen_job_map")
    loc_map_file = st.file_uploader("Upload Work Location Mapping (Optional)", type=["xlsx", "csv"], key="pc_gen_loc_map")
    
    if paycom_file:
        if st.button("Generate Uzio Template", type="primary"):
            with st.spinner("Processing..."):
                try:
                    if paycom_file.name.lower().endswith('.csv'):
                         try:
                             df_paycom = pd.read_csv(paycom_file, dtype=str)
                         except UnicodeDecodeError:
                             paycom_file.seek(0)
                             df_paycom = pd.read_csv(paycom_file, dtype=str, encoding='latin1')
                    else:
                         df_paycom = pd.read_excel(paycom_file, dtype=str)
                        
                    # Normalize source columns
                    df_paycom.columns = [norm_colname(c) for c in df_paycom.columns]
                    
                    # Normalize and Resolve the VENDOR_FIELD_MAP values
                    # We pick the first column name in the fallback list that actually exists in df_paycom
                    resolved_field_map = {}
                    for std_name, vendor_cols in PAYCOM_FIELD_MAP.items():
                        found = False
                        for vc in vendor_cols:
                            norm_vc = norm_colname(vc)
                            if norm_vc in df_paycom.columns:
                                resolved_field_map[std_name] = norm_vc
                                found = True
                                break
                        # If none found, just map to the first one so it defaults to blank downstream
                        if not found:
                            resolved_field_map[std_name] = norm_colname(vendor_cols[0])
                    
                    # Generate Uzio Template
                    df_uzio = generate_uzio_template(df_paycom, resolved_field_map)
                    
                    # Apply Job Title Mapping
                    src_job_col = resolved_field_map.get('Job Title')
                    if src_job_col and src_job_col in df_paycom.columns:
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
                            
                        df_uzio['Job Title'] = df_paycom[src_job_col].apply(map_job)
                    
                    # Apply Work Location Mapping
                    src_loc_col = resolved_field_map.get('Work Location')
                    if src_loc_col and src_loc_col in df_paycom.columns:
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
                            
                        df_uzio['Work Location'] = df_paycom[src_loc_col].apply(map_loc)
                    
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
