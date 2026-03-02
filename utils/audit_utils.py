import pandas as pd
import streamlit as st
import io

# --- Hardcoded Mappings ---

# Map Uzio Raw Headers -> Internal Standard Names
UZIO_RAW_MAPPING = {
    'Employee ID*': 'Employee ID',
    'Employee First Name*': 'First Name',
    'Employee Last Name*': 'Last Name',
    'Employee Middle Initial': 'Middle Initial',
    'Employee Suffix': 'Suffix',
    'Employment Status*': 'Employment Status',
    'Date of Hire*': 'Hire Date',
    'Original DOH': 'Original Hire Date',
    'Termination Date': 'Termination Date',
    'Termination Reason': 'Termination Reason',
    'Employment Type*': 'Employment Type',
    'Pay Type*': 'Pay Type',
    'Annual Salary(Digits)**': 'Annual Salary',
    'Hourly Pay Rate**': 'Hourly Pay Rate',
    'Working Hours per Week(Digits)**': 'Working Hours',
    'Job Title': 'Job Title',
    'Department': 'Department',
    'Official Email*': 'Work Email',
    'Personal Email': 'Personal Email',
    'Phone Number(Digits)': 'Phone Number',
    'Employee SSN': 'SSN',
    'Employee Date of Birth*': 'DOB',
    'Employee Gender*': 'Gender',
    'Employee Tobacco usage in last 12 months': 'Tobacco User',
    'FLSA Classification': 'FLSA Classification',
    'Employee Address Line 1': 'Address Line 1',
    'Employee Address Line 2': 'Address Line 2',
    'City*': 'City',
    'Zipcode*': 'Zip',
    'State(Abbreviation)*': 'State',
    'Mailing Address Line 1': 'Mailing Address Line 1',
    'Mailing Address Line 2': 'Mailing Address Line 2',
    'Mailing City': 'Mailing City',
    'Mailing Zipcode': 'Mailing Zip',
    'Mailing State(Abbreviation)': 'Mailing State',
    'Reporting Manager ID': 'Reports To ID',
    'Work Location': 'Work Location'
}

def read_uzio_raw_file(uploaded_file):
    """
    Reads the raw Uzio .xlsm export.
    Expects 'Employee Details' sheet.
    Headers are in Row 4 (Index 3).
    Renames columns to Internal Standard Names.
    """
    try:
        # Read Excel - header=3 means 4th row is header
        df = pd.read_excel(uploaded_file, sheet_name='Employee Details', header=3)
        
        # Strip whitespace and replace newlines/multiple spaces with single space
        df.columns = df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
        
        # Rename columns based on mapping
        # Only rename columns that exist in the mapping
        rename_dict = {k: v for k, v in UZIO_RAW_MAPPING.items() if k in df.columns}
        df = df.rename(columns=rename_dict)
        
        # Ensure 'Employee ID' is string (remove decimals if any)
        if 'Employee ID' in df.columns:
            df['Employee ID'] = df['Employee ID'].astype(str).str.replace(r'\.0$', '', regex=True)
            
        print("Uzio Raw File Read Successfully.")
        print(f"Columns Found: {list(df.columns)}")
        return df

    except Exception as e:
        st.error(f"Error reading Uzio Raw File: {e}")
        return None

def norm_col(c):
    """Normalize column names to be case-insensitive and stripped."""
    if c is None: return ""
    return str(c).strip().replace("\n", " ").strip()

def clean_money_val(x):
    """Parse money/percentage strings to float. Returns original string if not a number."""
    if pd.isna(x) or x == "":
        return 0.0
    s = str(x).strip()
    s_clean = s.replace("$", "").replace("%", "").replace(",", "")
    s_clean = s_clean.replace("(", "-").replace(")", "") # Handle accounting negative
    try:
        return float(s_clean)
    except:
        return 0.0

def generate_uzio_template(df_source, vendor_field_map):
    """
    Generate an Uzio Census Template DataFrame from a source DataFrame.
    """
    
    # Create an empty dataframe with Uzio headers
    uzio_headers = list(UZIO_RAW_MAPPING.keys())
    df_uzio = pd.DataFrame(columns=uzio_headers)
    
    # Iterate through each Uzio expected header
    for uzio_header, std_name in UZIO_RAW_MAPPING.items():
        # Special Case: Leave blank
        if std_name in ['Job Title', 'Department', 'Termination Reason', 'Work Location']:
            df_uzio[uzio_header] = ""
            continue
            
        vendor_col = vendor_field_map.get(std_name)
        if vendor_col and vendor_col in df_source.columns:
            # We have a direct mapping
            series = df_source[vendor_col].copy()
            
            # Apply formatting rules
            if std_name == 'Middle Initial':
                series = series.apply(lambda x: str(x).strip()[0] if pd.notna(x) and str(x).strip() else "")
            elif std_name in ['Hire Date', 'Original Hire Date', 'Termination Date', 'DOB']:
                def format_date(d):
                    if pd.isna(d) or str(d).strip() == "": return ""
                    try:
                        dt = pd.to_datetime(str(d).strip(), errors='coerce')
                        if pd.isna(dt): return str(d).strip()
                        return dt.strftime('%d/%m/%Y')
                    except:
                        return str(d).strip()
                series = series.apply(format_date)
            elif std_name == 'SSN':
                series = series.apply(lambda x: str(x).replace("-", "").strip() if pd.notna(x) else "")
            elif std_name == 'Gender':
                def format_gender(g):
                    if pd.isna(g) or str(g).strip() == "": return ""
                    g_str = str(g).strip().lower()
                    if g_str.startswith('m'): return "Male"
                    if g_str.startswith('f'): return "Female"
                    return ""
                series = series.apply(format_gender)
            elif std_name == 'Employment Status':
                series = series.apply(lambda x: str(x).strip().upper() if pd.notna(x) else "")
            elif std_name in ['Zip', 'Mailing Zip']:
                def format_zip(z):
                    if pd.isna(z) or str(z).strip() == "": return ""
                    # Keep digits only
                    import re
                    z_clean = re.sub(r'\D', '', str(z).strip())
                    if not z_clean: return ""
                    # Pad to 5 or truncate to 5
                    if len(z_clean) < 5:
                        return z_clean.zfill(5)
                    else:
                        return z_clean[:5]
                series = series.apply(format_zip)
            elif std_name == 'Employment Type':
                def format_emp_type(et):
                    if pd.isna(et) or str(et).strip() == "": return ""
                    et_str = str(et).strip().lower()
                    if 'full' in et_str: return 'Full Time'
                    if 'part' in et_str: return 'Part Time'
                    if 'season' in et_str: return 'Seasonal'
                    if 'other' in et_str: return 'Other'
                    return ""
                series = series.apply(format_emp_type)
            # We port the data
            df_uzio[uzio_header] = series
        else:
            df_uzio[uzio_header] = ""

    # Apply Work Email Fallback
    if 'Official Email*' in df_uzio.columns and 'Personal Email' in df_uzio.columns:
        # Fill missing Work Emails with Personal Email
        missing_work_mask = df_uzio['Official Email*'].isna() | (df_uzio['Official Email*'].astype(str).str.strip() == "")
        df_uzio.loc[missing_work_mask, 'Official Email*'] = df_uzio.loc[missing_work_mask, 'Personal Email']

    # Apply Pay Type rules
    if 'Pay Type*' in df_uzio.columns:
        pay_type_series = df_uzio['Pay Type*'].astype(str).str.lower().str.strip()
        
        # Hourly logic
        hourly_mask = pay_type_series.str.contains('hour', na=False)
        df_uzio.loc[hourly_mask, 'Pay Type*'] = "Hourly"
        if 'Annual Salary(Digits)**' in df_uzio.columns:
            df_uzio.loc[hourly_mask, 'Annual Salary(Digits)**'] = ""
        # Enforce Hourly = Non-Exempt
        if 'FLSA Classification' in df_uzio.columns:
            df_uzio.loc[hourly_mask, 'FLSA Classification'] = "Non-Exempt"
            
        # Salaried logic
        salary_mask = pay_type_series.str.contains('salar', na=False)
        df_uzio.loc[salary_mask, 'Pay Type*'] = "Salaried"
        if 'Hourly Pay Rate**' in df_uzio.columns:
            df_uzio.loc[salary_mask, 'Hourly Pay Rate**'] = 0
        if 'Working Hours per Week(Digits)**' in df_uzio.columns:
            df_uzio.loc[salary_mask, 'Working Hours per Week(Digits)**'] = ""
        # Enforce Salaried = Exempt
        if 'FLSA Classification' in df_uzio.columns:
            df_uzio.loc[salary_mask, 'FLSA Classification'] = "Exempt"
            
        # Mandatory fallback: if FLSA is still blank, default to Non-Exempt as a safety measure
        if 'FLSA Classification' in df_uzio.columns:
            blank_flsa_mask = df_uzio['FLSA Classification'].isna() | (df_uzio['FLSA Classification'].astype(str).str.strip() == "")
            df_uzio.loc[blank_flsa_mask, 'FLSA Classification'] = "Non-Exempt"
            
    return df_uzio

def inject_into_uzio_template(df_uzio, template_path="templates/Uzio_Census_Template.xlsm"):
    """
    Injects a formatted Uzio DataFrame into the standard Uzio .xlsm template.
    Preserves all sheets, instructions, and headers.
    Dynamically finds the row containing 'Employee First Name*' and starts data on the next row.
    """
    import openpyxl
    import os
    import re
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found at {template_path}")
        
    wb = openpyxl.load_workbook(template_path, keep_vba=True)
    ws = wb['Employee Details']
    
    # Dynamically find the header row
    header_row = 4 # Fallback
    headers_in_template = {}
    
    for r in range(1, 10): # Search first 10 rows
        for c in range(1, ws.max_column + 1):
            val = ws.cell(row=r, column=c).value
            if val and re.sub(r'\s+', ' ', str(val)).strip() == 'Employee First Name*':
                header_row = r
                break
        if header_row == r:
            break
            
    # Map column headers
    for col_idx in range(1, ws.max_column + 1):
        val = ws.cell(row=header_row, column=col_idx).value
        if val:
            # Normalize to handle templates with embedded newlines like 'Employment\nStatus*'
            norm_val = re.sub(r'\s+', ' ', str(val)).strip()
            headers_in_template[norm_val] = col_idx

    # Write data starting at the row after the headers
    start_row = header_row + 1

    for row_idx, row_data in df_uzio.iterrows():
        excel_row = start_row + row_idx
        for col_name in df_uzio.columns:
            c_name_strip = re.sub(r'\s+', ' ', str(col_name)).strip()
            if c_name_strip in headers_in_template:
                col_idx = headers_in_template[c_name_strip]
                val = row_data[col_name]
                if pd.notna(val) and val != "":
                    ws.cell(row=excel_row, column=col_idx, value=val)
                    
    return wb

def validate_uzio_data(df_uzio):
    """
    Validates required fields for Uzio Census.
    Returns a DataFrame containing Employee ID and the list of missing fields.
    Fields checked: Pay Type*, Employment Status*, Job Title, Work Location.
    """
    errors = []
    
    # Identify expected column names from UZIO_RAW_MAPPING vs what's in df_uzio
    # Or just use the exact Uzio headers if df_uzio has them
    emp_id_col = 'Employee ID*' if 'Employee ID*' in df_uzio.columns else 'Employee ID'
    
    for idx, row in df_uzio.iterrows():
        emp_id = row.get(emp_id_col, f"Row {idx+1}")
        if pd.isna(emp_id) or str(emp_id).strip() == "":
            emp_id = f"Row {idx+1}"
            
        missing_fields = []
        
        # Check Pay Type
        val_pt = row.get('Pay Type*')
        if pd.isna(val_pt) or str(val_pt).strip() == "":
            missing_fields.append("Pay Type")
            
        # Check Employment Status
        val_es = row.get('Employment Status*')
        if pd.isna(val_es) or str(val_es).strip() == "":
            missing_fields.append("Employment Status")
            
        # Check Job Title
        val_jt = row.get('Job Title')
        if pd.isna(val_jt) or str(val_jt).strip() == "":
            missing_fields.append("Job Title")
            
        # Check Work Location
        val_wl = row.get('Work Location')
        if pd.isna(val_wl) or str(val_wl).strip() == "":
            missing_fields.append("Work Location")
            
        if missing_fields:
            errors.append({
                "Employee ID": emp_id,
                "Missing Fields": ", ".join(missing_fields),
                "Error": "Mandatory fields are blank"
            })
            
    return pd.DataFrame(errors)
