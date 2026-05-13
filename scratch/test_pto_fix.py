"""Verify the Paycom Prior Payroll Audit no longer double-counts PTO across
Earnings + Employee Benefits Code Descriptions for DNI Carriers emp 165.

Expected after fix: emp 165 Paycom Paid Time Off total = 124.52 (Earnings only).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit_fast_api"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit_fast_api"))

import pandas as pd
from core.paycom.total_comparison import find_header_and_data_paycom, calculate_totals_paycom

paycom_file = r"C:\Users\shobhit.sharma\Downloads\DNI Prior Payroll Setup\DNI Carrier Prior Payroll -Q1- 12212025_03212026_03272026.xlsx - Employee YTD Bala.csv"

with open(paycom_file, "rb") as fh:
    content = fh.read()
fname = os.path.basename(paycom_file)
res = find_header_and_data_paycom(content, fname)
df = res[0] if isinstance(res, tuple) else res
print(f"Loaded {len(df)} rows. Columns: {list(df.columns)[:10]}...")

emp_id_col = next((c for c in df.columns if "ee code" in str(c).lower() or "associate" in str(c).lower()), None)
df_165 = df[df[emp_id_col].astype(str).str.strip() == "165"]
print(f"\nEmp 165 rows: {len(df_165)}")
type_desc_col = next((c for c in df.columns if "type description" in str(c).lower()), None)
code_desc_col = next((c for c in df.columns if "code description" in str(c).lower()), None)
amt_col = next((c for c in df.columns if "amount" in str(c).lower()), None)
pto_rows = df_165[df_165[type_desc_col].astype(str).str.strip() == "Paid Time Off"]
print(f"\nEmp 165 PTO rows ({len(pto_rows)}):")
print(pto_rows[[type_desc_col, code_desc_col, amt_col]].to_string(index=False))

total, found, emp_tots = calculate_totals_paycom(
    df, ["Paid Time Off"], filename=os.path.basename(paycom_file), uzio_item_name="Paid Time Off"
)

emp_165_amt = sum(v for (eid, _), v in emp_tots.items() if str(eid) == "165")
print(f"\n>>> Emp 165 Paycom Paid Time Off total AFTER FIX: {emp_165_amt}")
print(f">>> Expected: 124.52 (Earnings only — 5.66 Employee Benefits should be excluded)")
assert abs(emp_165_amt - 124.52) < 0.01, f"FAIL: got {emp_165_amt}, expected 124.52"
print("\nPASS — Employee Benefits PTO row is excluded.")
