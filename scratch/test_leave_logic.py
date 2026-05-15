
import pandas as pd
import sys
import os

# Add root to sys.path
sys.path.append(os.getcwd())

from apps.paycom.census_generator import preprocess_paycom_file, render_auto_fix_options

def test_leave_logic():
    # We'll create a dummy dataframe to test the logic since we don't have a leave file handy
    # But we can also just use the existing logic inside the script.
    
    data = {
        'Employee_Code': ['L1', 'L2'],
        'Legal_Firstname': ['Leave', 'Terminated'],
        'Legal_Lastname': ['User', 'User'],
        'Employee_Status': ['On Leave', 'On Leave'],
        'Termination_Date': ['', '05/15/2026'],
        'DOL_Status': ['Full Time', 'Full Time'],
        'Pay_Type': ['Hourly', 'Hourly'],
        'Position': ['Driver', 'Driver'],
        'Exempt_Status': ['Non-Exempt', 'Non-Exempt'],
        'Work_Location': ['Loc1', 'Loc1']
    }
    df_paycom = pd.DataFrame(data)
    
    # Simulate field mapping
    resolved_field_map = {
        'Employment Status': 'Employee_Status',
        'Termination Date': 'Termination_Date',
        'Employee ID': 'Employee_Code'
    }
    
    print("Testing 'On Leave' Logic...")
    
    df_download = df_paycom.copy()
    audit_trail = []
    def log_change(idx, field, old, new, comment):
        audit_trail.append({'ID': df_download.at[idx, 'Employee_Code'], 'Field': field, 'Old': old, 'New': new, 'Comment': comment})

    # --- Logic under test ---
    c_pos = resolved_field_map.get('Employment Status')
    c_term = resolved_field_map.get('Termination Date')
    pos_series = df_download[c_pos].astype(str).str.strip().str.lower()
    term_series = df_download[c_term].astype(str).str.strip().str.lower()
    
    mask_leave = pos_series.str.contains('leave', na=False)
    mask_term_blank = df_download[c_term].isna() | (term_series == "") | (term_series == "nan")
    
    # Case A: On Leave & No Term Date -> Active (Exclude from Payroll)
    for idx in df_download[mask_leave & mask_term_blank].index:
        old_p = df_download.at[idx, c_pos]
        df_download.at[idx, c_pos] = "Active"
        log_change(idx, "Employment Status", old_p, "Active", "Excluded from payroll")
    
    # Case B: On Leave & HAS Term Date -> Terminated
    for idx in df_download[mask_leave & ~mask_term_blank].index:
        old_p = df_download.at[idx, c_pos]
        df_download.at[idx, c_pos] = "Terminated"
        log_change(idx, "Employment Status", old_p, "Terminated", "Converted 'Leave' to 'Terminated' due to presence of Termination Date.")

    print("\nResults:")
    for idx, row in df_download.iterrows():
        print(f"ID: {row['Employee_Code']}, Status: {row[c_pos]}, Term Date: {row[c_term]}")
    
    print("\nAudit Trail:")
    for entry in audit_trail:
        print(f"ID: {entry['ID']}, New Status: {entry['New']}, Comment: {entry['Comment']}")

if __name__ == "__main__":
    test_leave_logic()
