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
    'SOC Code': ['SOC Code']
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
                    
                    # Generate Uzio Template
                    df_uzio = generate_uzio_template(df_adp, resolved_field_map)
                    
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
