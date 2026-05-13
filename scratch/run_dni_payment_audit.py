"""Run the Paycom payment audit for DNI Carriers."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit_fast_api"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit_fast_api"))

from datetime import datetime
import pandas as pd
from core.paycom.payment_audit import run_paycom_payment_audit

uzio_path = r"C:\Users\shobhit.sharma\Downloads\DNI Prior Payroll Setup\DNI Carriers Uzio Payment Method Report 05th May.xlsx"
paycom_path = r"C:\Users\shobhit.sharma\Downloads\DNI Prior Payroll Setup\DNI Carriers - FIT_SIT_PaymentMethod_WKC.xlsx - Report Data.csv"

with open(uzio_path, "rb") as f:
    uzio_content = f.read()
with open(paycom_path, "rb") as f:
    paycom_content = f.read()

print(f"Uzio file: {len(uzio_content):,} bytes")
print(f"Paycom file: {len(paycom_content):,} bytes")

results = run_paycom_payment_audit(uzio_content, paycom_content)

stamp = datetime.now().strftime("%Y%m%d_%H%M")
out_dir = r"C:\Users\shobhit.sharma\Desktop\Audit Files"
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, f"DNI_Carriers_Paycom_Payment_Audit_{stamp}.xlsx")

with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
    for sheet, data in results.items():
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name=sheet[:31], index=False)

print(f"\nReport written: {out_path}\n")

# Print summary so user sees it without opening the file
print("=== Summary ===")
for r in results["Summary"]:
    print(f"  {r['Metric']}: {r['Value']}")

print("\n=== Field Summary By Status ===")
fs = pd.DataFrame(results["Field_Summary_By_Status"])
if not fs.empty:
    print(fs.to_string(index=False))
else:
    print("(empty)")

cd = pd.DataFrame(results["Comparison_Detail_AllFields"])
print(f"\n=== Comparison Detail: {len(cd):,} rows ===")
if not cd.empty:
    not_match = cd[cd["Paycom_SourceOfTruth_Status"] != "Data Match"]
    print(f"Rows that are NOT 'Data Match': {len(not_match):,}")
    by_status = not_match["Paycom_SourceOfTruth_Status"].value_counts()
    print("\nBreakdown:")
    for status, n in by_status.items():
        print(f"  {status}: {n}")
