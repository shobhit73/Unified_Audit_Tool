import pandas as pd
import re
import numpy as np

# --- MAPPINGS ---
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

ADP_FIELD_MAP = {
    'Employee ID': 'Associate ID',
    'First Name': 'Legal First Name',
    'Last Name': 'Legal Last Name',
    'Middle Initial': 'Legal Middle Name',
    'Employment Status': 'Position Status',
    'Hire Date': 'Hire/Rehire Date',
    'Original Hire Date': 'Hire Date',
    'Termination Date': 'Termination Date',
    'Termination Reason': 'Termination Reason Description',
    'Pay Type': 'Regular Pay Rate Description',
    'Annual Salary': 'Annual Salary',
    'Hourly Pay Rate': 'Regular Pay Rate Amount',
    'Working Hours': 'Regular Hours',
    'Job Title': 'Job Title Description',
    'Department': 'Department Description',
    # 'Work Email': 'Work Contact: Work Email', # Removed as not found
    'Personal Email': 'Personal Contact: Personal Email',
    # 'Phone Number': 'Personal Contact: Personal Mobile', # Removed
    'SSN': 'Tax ID (SSN)',
    'DOB': 'Birth Date',
    'Gender': 'Gender (Self-ID)',
    'Tobacco User': 'Tobacco User',
    'FLSA Classification': 'FLSA Description',
    'Address Line 1': 'Primary Address: Address Line 1',
    'Address Line 2': 'Primary Address: Address Line 2',
    'City': 'Primary Address: City',
    'Zip': 'Legal / Preferred Address: Zip / Postal Code',
    'State': 'Primary Address: State / Territory Code',
    'Mailing Address Line 1': 'Legal / Preferred Address: Address Line 1',
    'Mailing Address Line 2': 'Legal / Preferred Address: Address Line 2',
    'Mailing City': 'Legal / Preferred Address: City',
    'Mailing Zip': 'Legal / Preferred Address: Zip / Postal Code',
    'Mailing State': 'Legal / Preferred Address: State / Territory Code',
    'Reports To ID': 'Reports To Associate ID',
    'Protected Veteran Status': 'Protected Veteran Status',
    'EEO Job Category': 'EEOC Job Classification', 
    'Ethnicity': 'Ethnicity',
    'SOC Code': 'SOC Code'
}

PAYCOM_FIELD_MAP = {
    'Employee ID': 'Employee_Code',
    'First Name': 'Legal_Firstname',
    'Last Name': 'Legal_Lastname',
    'Middle Initial': 'Legal_Middle_Name',
    'Employment Status': 'Employee_Status',
    'Hire Date': 'Most_Recent_Hire_Date',
    'Original Hire Date': 'Most_Recent_Hire_Date',
    'Termination Date': 'Termination_Date',
    # 'Termination Reason': 'Termination_Reason', # Removed
    'Pay Type': 'Pay_Type',
    'Annual Salary': 'Rate_1',
    'Hourly Pay Rate': 'Rate_1',
    'Working Hours': 'Scheduled_Pay_Period_Hours',
    'Job Title': 'Position',
    'Department': 'Department',
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
    'Mailing State': 'Mailing_State/Province'
}


def norm_colname(c: str) -> str:
    if c is None: return ""
    c = str(c).replace("\n", " ").replace("\r", " ").replace("\u00A0", " ")
    c = c.replace("’", "'").replace("“", '"').replace("”", '"')
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "").strip('"').strip("'")
    return c

# Helper to write to file
def log(msg):
    print(msg)
    with open("verify_report_utf8.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# Clear file first
with open("verify_report_utf8.txt", "w", encoding="utf-8") as f:
    f.write("Verification Report\n")

def verify_mapping(name, mapping, actual_cols, normalize_fn=None):
    log(f"\n--- Verifying {name} ---")
    missing = []
    
    if normalize_fn:
        norm_actual = {normalize_fn(c): c for c in actual_cols}
        for key, expected_col in mapping.items():
            norm_expected = normalize_fn(expected_col)
            if norm_expected in norm_actual:
                log(f"[PASS] {key}: Found '{norm_actual[norm_expected]}'")
            else:
                log(f"[FAIL] {key}: Expected '{expected_col}' (norm: '{norm_expected}') NOT FOUND")
                missing.append(key)
    else:
        cleaned_cols = set(actual_cols)
        for key in mapping.keys():
             if key in cleaned_cols:
                  log(f"[PASS] {key}: Found")
             else:
                  log(f"[FAIL] {key}: NOT FOUND")
                  missing.append(key)

    if not missing:
        log(f"ALL {name} MAPPINGS VALID")
    else:
        log(f"{len(missing)} {name} MAPPINGS FAILED")

# 1. Uzio
log("Loading Uzio...")
try:
    uzio_df = pd.read_excel(r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Multi_Client_East West Logistix_Employee_Census (2) (1).xlsm", sheet_name='Employee Details', header=3)
    uzio_df.columns = uzio_df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
    verify_mapping("UZIO", UZIO_RAW_MAPPING, uzio_df.columns)
except Exception as e:
    log(f"Error loading Uzio: {e}")

# 2. ADP
log("\nLoading ADP...")
try:
    adp_df = pd.read_excel(r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\ADP Cenus File.xlsx")
    adp_norm_cols = [norm_colname(c) for c in adp_df.columns]
    
    missing_adp = []
    log("\n--- Verifying ADP ---")
    for internal_key, adp_col_name in ADP_FIELD_MAP.items():
        if not adp_col_name: continue
        target = norm_colname(adp_col_name)
        if target in adp_norm_cols:
            log(f"[PASS] {internal_key}: Found '{target}'")
        else:
            log(f"[FAIL] {internal_key}: Expected '{adp_col_name}' (norm: '{target}')")
            missing_adp.append(internal_key)

    if not missing_adp:
        log("ALL ADP MAPPINGS VALID")
    else:
        log(f"{len(missing_adp)} ADP MAPPINGS FAILED")

except Exception as e:
    log(f"Error loading ADP: {e}")

# 3. Paycom
log("\nLoading Paycom...")
try:
    paycom_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus File.csv"
    try:
        paycom_df = pd.read_csv(paycom_path, dtype=str)
    except:
        paycom_df = pd.read_csv(paycom_path, dtype=str, encoding='latin1')
        
    paycom_norm_cols = [norm_colname(c) for c in paycom_df.columns]
    
    missing_paycom = []
    log("\n--- Verifying Paycom ---")
    for internal_key, paycom_col_name in PAYCOM_FIELD_MAP.items():
        if not paycom_col_name: continue
        target = norm_colname(paycom_col_name)
        if target in paycom_norm_cols:
            log(f"[PASS] {internal_key}: Found '{target}'")
        else:
            log(f"[FAIL] {internal_key}: Expected '{paycom_col_name}' (norm: '{target}')")
            missing_paycom.append(internal_key)
            
    if not missing_paycom:
        log("ALL PAYCOM MAPPINGS VALID")
    else:
        log(f"{len(missing_paycom)} PAYCOM MAPPINGS FAILED")

except Exception as e:
    log(f"Error loading Paycom: {e}")
