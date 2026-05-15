
import pandas as pd
import sys
import os

# Add root to sys.path
sys.path.append(os.getcwd())

from apps.paycom.census_generator import preprocess_paycom_file, render_auto_fix_options

def test_ui_warning():
    data = {
        'Employee_Code': ['L1'],
        'Legal_Firstname': ['Leave'],
        'Legal_Lastname': ['User'],
        'Employee_Status': ['On Leave'],
        'Termination_Date': [''],
    }
    df_source = pd.DataFrame(data)
    
    # Mock row
    row = df_source.iloc[0]
    status_lower = 'on leave'
    status_val = 'On Leave'
    term_date_col = 'Termination_Date'
    emp_ref = 'L1'
    anomalies = []
    
    # --- Logic from audit_utils.py ---
    is_leave = 'leave' in status_lower
    if is_leave:
        if term_date_col and term_date_col in df_source.columns:
            tdate = row.get(term_date_col)
            if pd.isna(tdate) or str(tdate).strip() == "" or str(tdate).lower() == "nan":
                anomalies.append({
                    'Employee ID': emp_ref,
                    'Issue': f"On Leave Employee ({status_val})",
                    'Message': "Please make them excluded from payroll on Uzio"
                })

    print("Testing UI Anomaly Generation...")
    print(f"Anomalies: {anomalies}")

if __name__ == "__main__":
    test_ui_warning()
