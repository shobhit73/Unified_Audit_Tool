import pandas as pd
import io
import os
from paycom_payment_audit_app import run_audit

# Path to real Uzio Payment Raw
uzio_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Payment Data\HR Report_2026-02-13-05-00-13.xlsx"

# Create a mock Paycom file
# We need to match at least one employee from Uzio to see a match.
# From inspection:
# 'Company Name', 'Full Name', 'Employee ID', 'Payment Method', ...
# Let's read Uzio first to get an ID.

print("Reading Uzio for mock data...")
df_uzio = pd.read_excel(uzio_path, header=1, dtype=str)
first_emp = df_uzio.iloc[0]
emp_id = first_emp.get("Employee ID")
print(f"Found Employee ID: {emp_id}")

# Create mock paycom data
# Columns needed: Employee_Code, Net_Acct_Code, Net_Rout_Code, Net_Type_Code
data = {
    "Employee_Code": [emp_id, "99999"],
    "Net_Acct_Code": ["123456789", "987654321"],
    "Net_Rout_Code": ["123456789", "987654321"],
    "Net_Type_Code": ["Checking", "Savings"],
    # Add some dist columns just in case
    "Dist_1_Acct_Code": ["", ""],
    "Dist_1_Rout_Code": ["", ""],
    "Dist_1_Amount": ["0", "0"],
    "Dist_1_Percent": ["0", "0"],
    "Dist_1_Type_Code": ["", ""]
}
df_paycom = pd.DataFrame(data)
paycom_path = "Mock_Paycom_Payment.xlsx"
df_paycom.to_excel(paycom_path, index=False)
print(f"Created mock Paycom file: {paycom_path}")

print("Running Audit...")
try:
    with open(uzio_path, "rb") as f_uzio, open(paycom_path, "rb") as f_paycom:
        report_bytes = run_audit(f_uzio, f_paycom)
    
    print("Audit successful! Saving details...")
    with open("Payment_Audit_Result.xlsx", "wb") as f_out:
        f_out.write(report_bytes)
        
    # Inspect result
    df_res = pd.read_excel("Payment_Audit_Result.xlsx", sheet_name="Summary")
    print("Summary Sheet:")
    print(df_res)
    
    df_field = pd.read_excel("Payment_Audit_Result.xlsx", sheet_name="Field_Summary_By_Status")
    print("\nField Summary:")
    print(df_field[['Field', 'Total', 'Value missing in Uzio (Paycom has value)', 'Value missing in Paycom (Uzio has value)']])
    
except Exception as e:
    print(f"Audit FAILED: {e}")
    # Print full traceback
    import traceback
    traceback.print_exc()
