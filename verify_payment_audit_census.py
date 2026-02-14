import pandas as pd
import io
import os
from paycom_payment_audit_app import run_audit

# Path to real Uzio Payment Raw
uzio_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Payment Data\HR Report_2026-02-13-05-00-13.xlsx"

# Path to real Paycom Census
paycom_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus Sample\Pria Paycom Cenus.xlsx"

print("Running Audit with Real Census...")
try:
    if not os.path.exists(uzio_path):
        print(f"Uzio file not found: {uzio_path}")
    if not os.path.exists(paycom_path):
        print(f"Paycom file not found: {paycom_path}")
        
    with open(uzio_path, "rb") as f_uzio, open(paycom_path, "rb") as f_paycom:
        report_bytes = run_audit(f_uzio, f_paycom)
    
    print("Audit successful! Saving details...")
    with open("Payment_Audit_Census_Result.xlsx", "wb") as f_out:
        f_out.write(report_bytes)
        
    # Inspect result
    df_res = pd.read_excel("Payment_Audit_Census_Result.xlsx", sheet_name="Summary")
    print("Summary Sheet:")
    print(df_res)
    
    df_field = pd.read_excel("Payment_Audit_Census_Result.xlsx", sheet_name="Field_Summary_By_Status")
    print("\nField Summary:")
    print(df_field[['Field', 'Total', 'Data Match', 'Data Mismatch']])
    
except Exception as e:
    print(f"Audit FAILED: {e}")
    # Print full traceback
    import traceback
    traceback.print_exc()
