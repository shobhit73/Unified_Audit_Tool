
import pandas as pd
import sys
import os

# Add root to sys.path
sys.path.append(os.getcwd())

from apps.paycom.census_generator import preprocess_paycom_file, render_auto_fix_options

def test_logic():
    file_path = r"C:\Users\shobhit.sharma\Downloads\Chief Logistics\Chief Census Paycom Report 14th May.csv"
    print(f"Reading file: {file_path}")
    
    # Simulate Streamlit file uploader by reading into BytesIO if needed, 
    # but preprocess_paycom_file accepts a file-like object.
    with open(file_path, 'rb') as f:
        df_paycom, original_columns, norm_to_orig, resolved_field_map = preprocess_paycom_file(f)

    if df_paycom is None:
        print("Failed to preprocess file.")
        return

    # Check Joshua Meyer (Row 751 in user's Excel, which might be different index in pandas)
    # The user's screenshot shows Employee_Code 'A0CC' for Joshua Meyer.
    emp_id_col = resolved_field_map.get('Employee ID')
    target_id = 'A0CC'
    
    print(f"Targeting Employee ID: {target_id}")
    
    # Get current state
    target_row = df_paycom[df_paycom[emp_id_col].astype(str).str.strip() == target_id]
    if target_row.empty:
        print(f"Employee {target_id} not found.")
        return
    
    idx = target_row.index[0]
    c_flsa = resolved_field_map.get('FLSA Classification')
    c_pt = resolved_field_map.get('Pay Type')
    c_jt = resolved_field_map.get('Job Title')
    
    print(f"Initial State for {target_id}:")
    print(f"  Job Title: {df_paycom.at[idx, c_jt]}")
    print(f"  Pay Type: {df_paycom.at[idx, c_pt]}")
    print(f"  FLSA: {df_paycom.at[idx, c_flsa]}")

    # Simulate the fix logic
    fix_options = render_auto_fix_options("test")
    df_download = df_paycom.copy()
    audit_trail = []

    def log_change(row_idx, field, old_val, new_val, comment):
        audit_trail.append({'ID': target_id, 'Field': field, 'Old': old_val, 'New': new_val, 'Comment': comment})

    # --- Implementation of the new logic (copied from census_generator.py) ---
    if fix_options.get('fix_flsa'):
        if c_flsa and c_flsa in df_download.columns:
            # Priority 1: Drivers
            if c_jt and c_jt in df_download.columns:
                mask_jt_driver = df_download[c_jt].astype(str).str.lower().str.contains("driver|helper", na=False)
                mask_flsa_blank = df_download[c_flsa].isna() | (df_download[c_flsa].astype(str).str.strip().str.lower().isin(["nan", ""]))
                for i in df_download[mask_jt_driver & mask_flsa_blank].index:
                    old_f = df_download.at[i, c_flsa]
                    df_download.at[i, c_flsa] = "Non-Exempt"
                    log_change(i, "FLSA Classification", old_f, "Non-Exempt", "Set Non-Exempt for Driver/Helper role.")

            # Priority 2 & 3: Pay Type Based
            if c_pt and c_pt in df_download.columns:
                mask_flsa_blank = df_download[c_flsa].isna() | (df_download[c_flsa].astype(str).str.strip().str.lower().isin(["nan", ""]))
                for i in df_download[mask_flsa_blank].index:
                    pt_val = str(df_download.at[i, c_pt]).lower().strip()
                    old_f = df_download.at[i, c_flsa]
                    if 'hourly' in pt_val:
                        df_download.at[i, c_flsa] = "Non-Exempt"
                        log_change(i, "FLSA Classification", old_f, "Non-Exempt", "Set Non-Exempt based on Hourly pay type.")
                    elif 'salary' in pt_val or 'salaried' in pt_val:
                        df_download.at[i, c_flsa] = "Exempt"
                        log_change(i, "FLSA Classification", old_f, "Exempt", "Set Exempt based on Salary/Salaried pay type.")

    print(f"\nFinal State for {target_id}:")
    print(f"  FLSA: {df_download.at[idx, c_flsa]}")
    
    if audit_trail:
        print("\nAudit Trail Entries for this employee:")
        for entry in audit_trail:
            if entry['ID'] == target_id:
                print(f"  {entry['Comment']} (Old: {entry['Old']}, New: {entry['New']})")
    else:
        print("\nNo changes made to this employee.")

if __name__ == "__main__":
    test_logic()
