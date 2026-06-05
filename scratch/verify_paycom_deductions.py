"""Verify extraction + Match/Memo bifurcation on Chief Delivery."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.prior_payroll_setup_helper import (
    extract_unique_deductions_from_prior, bifurcate_match_memo,
)

PATH = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv"

df = pd.read_csv(PATH, dtype=str)
all_deds = extract_unique_deductions_from_prior(df)
contribs, deds = bifurcate_match_memo(all_deds)

print(f"Extracted {len(all_deds)} unique deductions from Prior Payroll.")
print(f"  -> {len(contribs)} Contributions (Match/Memo found)")
print(f"  -> {len(deds)} Deductions (everything else)")
print()
print(f"=== Contributions ({len(contribs)}) ===")
for r in contribs:
    print(f"  {r['Type Code']:<6s} {r['Type Description']}")
print()
print(f"=== Deductions ({len(deds)}) ===")
for r in deds:
    print(f"  {r['Type Code']:<6s} {r['Type Description']}")
