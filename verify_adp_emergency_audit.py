import pandas as pd
import io
import os
from adp_emergency_audit_app import run_audit

# Path to real inputs
uzio_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Uzio Emergeency Input File.xlsx"
adp_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\ADP Emegerncy Input .xlsx"

print("Running ADP Emergency Audit...")
try:
    if not os.path.exists(uzio_path):
        print(f"Uzio file not found: {uzio_path}")
    if not os.path.exists(adp_path):
        print(f"ADP file not found: {adp_path}")
        
    with open(uzio_path, "rb") as f_uzio, open(adp_path, "rb") as f_adp:
        report_bytes = run_audit(f_uzio, f_adp)
    
    print("Audit successful! Saving details...")
    with open("ADP_Emergency_Audit_Result.xlsx", "wb") as f_out:
        f_out.write(report_bytes)
        
    # Inspect result
    df_res = pd.read_excel("ADP_Emergency_Audit_Result.xlsx", sheet_name="Summary")
    print("Summary Sheet:")
    print(df_res)
    
    # Check details for a sample employee
    df_detail = pd.read_excel("ADP_Emergency_Audit_Result.xlsx", sheet_name="Emergency_Contact_Audit")
    print("\nSample Details (First 10 rows):")
    print(df_detail.head(10).to_string())

except Exception as e:
    print(f"Audit FAILED: {e}")
    import traceback
    traceback.print_exc()
