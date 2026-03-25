import pandas as pd
import sys
import os

# Ensure the parent directory is in the path
sys.path.append(os.path.abspath('.'))

from utils.audit_utils import generate_uzio_template, UZIO_RAW_MAPPING

def run_test():
    file_path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\data\Paycom_Census_Mark_Logistics_24th_March_2026.xlsx'
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    df_source = pd.read_excel(file_path)
    
    def norm_colname(c: str) -> str:
        import re
        if c is None: return ""
        c = str(c).replace("\n", " ").replace("\r", " ")
        c = re.sub(r'\(.*?\)', '', c)
        c = re.sub(r"\s+", " ", c).strip().replace("*", "")
        return c.lower()
    
    df_norm = df_source.copy()
    df_norm.columns = [norm_colname(c) for c in df_norm.columns]
    
    paycom_field_map_raw = {
        'Employee ID': ['Employee_Code'],
        'First Name': ['Legal_Firstname'],
        'Last Name': ['Legal_Lastname'],
        'Middle Initial': ['Legal_Middle_Name'],
        'Employment Status': ['Employee_Status'],
        'Employment Type': ['DOL_Status'],
        'Hire Date': ['Most_Recent_Hire_Date'],
        'Original Hire Date': ['Hire_Date'],
        'Termination Date': ['Termination_Date'],
        'Pay Type': ['Pay_Type'],
        'Job Title': ['Position'],
        'Department': ['Department_Desc'],
        'Work Email': ['Work_Email'],
        'Personal Email': ['Personal_Email'],
        'SSN': ['SS_Number'],
        'FLSA Classification': ['Exempt_Status'],
    }
    
    resolved_field_map = {}
    for std, cands in paycom_field_map_raw.items():
        for cand in cands:
            norm_cand = norm_colname(cand)
            if norm_cand in df_norm.columns:
                resolved_field_map[std] = norm_cand
                break
    
    fix_options = {
        'fix_flsa': True,
        'fix_emails': True,
        'fix_status': True,
        'fix_inactive': True,
        'fix_type': True,
        'fix_position': True,
        'fix_dol_status': True
    }
    
    print("TESTING PAYCOM DATA FIXES")
    print("-" * 50)
    
    df_uzio = generate_uzio_template(df_norm, resolved_field_map, fix_options)
    
    # 1. Position Fallback (Jacob Row 4)
    # Jesus Row 11
    test_rows_pos = [2, 9] # Indices for Jacob and Jesus (Rank 2 and Rank 9)
    for i in test_rows_pos:
        orig_p = f"Row {i+2}"
        orig_pos = str(df_norm.loc[i, 'position']).strip()
        orig_dept = str(df_norm.loc[i, 'department_desc']).strip()
        final_pos = str(df_uzio.loc[i, 'Job Title']).strip()
        print(f"[POS-CHECK] {orig_p}: Original Pos: '{orig_pos}', Dept_Desc: '{orig_dept}', Final Uzio Position: '{final_pos}'")
    
    # 2. DOL Status Fallback (Check Terminated vs Active)
    mask_dol_blank = df_norm['dol_status'].isna() | (df_norm['dol_status'].astype(str).str.strip() == "")
    idx_dol = df_norm[mask_dol_blank].index
    if not idx_dol.empty:
        print(f"[DOL-CHECK] Blank DOL Statuses found: {len(idx_dol)}")
        for i in idx_dol[:3]:
            status = str(df_norm.loc[i, 'employee_status']).strip()
            final_et = str(df_uzio.loc[i, 'Employment Type*']).strip()
            print(f"  {i+2} ({status}) -> Uzio: '{final_et}'")
    
    # 3. Driver Rules (PT Hourly, FLSA Non-Exempt)
    # Identify a driver
    mask_drv = df_uzio['Job Title'].astype(str).str.lower().str.contains('driver', na=False)
    idx_drv = df_uzio[mask_drv].index
    if not idx_drv.empty:
        i = idx_drv[0]
        pos = df_uzio.loc[i, 'Job Title']
        pt = df_uzio.loc[i, 'Pay Type*']
        flsa = df_uzio.loc[i, 'FLSA Classification']
        print(f"[DRIVER-CHECK] Row {i+2}: Title '{pos}', Pay Type: '{pt}', FLSA: '{flsa}'")
        
    # 4. Email Fallback
    mask_e = df_norm['work_email'].isna() | (df_norm['work_email'].astype(str).str.strip() == "")
    idx_e = df_norm[mask_e].index
    if not idx_e.empty:
        i = idx_e[0]
        pers = str(df_norm.loc[i, 'personal_email']).strip()
        final_e = str(df_uzio.loc[i, 'Official Email*']).strip()
        print(f"[EMAIL-CHECK] Row {i+2}: Personal: '{pers}', Final Uzio Email: '{final_e}'")

    print("-" * 50)
    print("TEST COMPLETED")

if __name__ == "__main__":
    run_test()
