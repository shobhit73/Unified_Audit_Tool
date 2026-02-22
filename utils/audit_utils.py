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
    'Reporting Manager ID': 'Reports To ID'
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
        if std_name in ['Job Title', 'Department', 'Termination Reason']:
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
                        # Attempt to parse into standard format
                        dt = pd.to_datetime(str(d).strip(), errors='coerce')
                        if pd.isna(dt): return str(d).strip()
                        return dt.strftime('%d/%m/%Y')
                    except:
                        return str(d).strip()
                series = series.apply(format_date)
                
            # We port the data
            df_uzio[uzio_header] = series
        else:
            df_uzio[uzio_header] = ""

    # Apply Pay Type rules
    if 'Pay Type*' in df_uzio.columns:
        pay_type_series = df_uzio['Pay Type*'].astype(str).str.lower().str.strip()
        
        # Hourly logic
        hourly_mask = pay_type_series.str.contains('hour', na=False)
        if 'Annual Salary(Digits)**' in df_uzio.columns:
            df_uzio.loc[hourly_mask, 'Annual Salary(Digits)**'] = ""
            
        # Salaried logic
        salary_mask = pay_type_series.str.contains('salar', na=False)
        if 'Hourly Pay Rate**' in df_uzio.columns:
            df_uzio.loc[salary_mask, 'Hourly Pay Rate**'] = 0
        if 'Working Hours per Week(Digits)**' in df_uzio.columns:
            df_uzio.loc[salary_mask, 'Working Hours per Week(Digits)**'] = ""
            
    return df_uzio

def inject_into_uzio_template(df_uzio, template_path="templates/Uzio_Census_Template.xlsm"):
    """
    Injects a formatted Uzio DataFrame into the standard Uzio .xlsm template.
    Preserves all sheets, instructions, and headers.
    Data starts at Row 5 of the 'Employee Details' sheet.
    """
    import openpyxl
    import os
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found at {template_path}")
        
    wb = openpyxl.load_workbook(template_path, keep_vba=True)
    ws = wb['Employee Details']
    
    # Write data starting at row 5
    start_row = 5
    
    # We want to match the columns perfectly. The template has exact headers in row 4.
    headers_in_template = {}
    for col_idx in range(1, ws.max_column + 1):
        # We only really care about columns that exist in the UZIO_RAW_MAPPING
        val = ws.cell(row=4, column=col_idx).value
        headers_in_template[str(val).strip()] = col_idx

    for row_idx, row_data in df_uzio.iterrows():
        excel_row = start_row + row_idx
        for col_name in df_uzio.columns:
            # Find which column index this header corresponds to in the template
            c_name_strip = str(col_name).strip()
            if c_name_strip in headers_in_template:
                col_idx = headers_in_template[c_name_strip]
                val = row_data[col_name]
                if pd.notna(val) and val != "":
                    ws.cell(row=excel_row, column=col_idx, value=val)
                    
    return wb
