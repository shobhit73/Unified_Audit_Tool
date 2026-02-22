import io
import pandas as pd
import streamlit as st
from utils.audit_utils import generate_uzio_template

APP_TITLE = "Paycom to Uzio Census Template Generator"

PAYCOM_FIELD_MAP = {
    'Employee ID': 'Employee_Code',
    'First Name': 'Legal_Firstname',
    'Last Name': 'Legal_Lastname',
    'Middle Initial': 'Legal_Middle_Name',
    'Employment Status': 'Employee_Status',
    'Hire Date': 'Most_Recent_Hire_Date',
    'Original Hire Date': 'Most_Recent_Hire_Date',
    'Termination Date': 'Termination_Date',
    'Pay Type': 'Pay_Type',
    'Annual Salary': 'Annual_Salary',
    'Hourly Pay Rate': 'Rate_1',
    'Working Hours': 'Scheduled_Pay_Period_Hours',
    'Job Title': 'Position',
    'Department': 'Department_Desc',
    'Work Email': 'Work_Email',
    'Personal Email': 'Personal_Email',
    'Phone Number': 'Primary_Phone',
    'SSN': 'SS_Number',
    'DOB': 'Birth_Date_(MM/DD/YYYY)',
    'Gender': 'Gender',
    'Tobacco User': 'Tobacco_User',
    'FLSA Classification': 'Exempt_Status',
    'Address Line 1': 'Primary_Address_Line_1',
    'Address Line 2': 'Primary_Address_Line_2',
    'City': 'Primary_City/Municipality',
    'Zip': 'Primary_Zip/Postal_Code',
    'State': 'Primary_State/Province',
    'Mailing Address Line 1': 'Mailing_Address_Line_1',
    'Mailing Address Line 2': 'Mailing_Address_Line_2',
    'Mailing City': 'Mailing_City/Municipality',
    'Mailing Zip': 'Mailing_Zip/Postal_Code',
    'Mailing State': 'Mailing_State/Province',
    'License Number': 'DriversLicense'
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
                    
                    # Normalize the VENDOR_FIELD_MAP values
                    normalized_field_map = {k: norm_colname(v) for k, v in PAYCOM_FIELD_MAP.items()}
                    
                    # Generate Uzio Template
                    df_uzio = generate_uzio_template(df_paycom, normalized_field_map)
                    
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
