"""Verify the new extract_unique_earnings_from_prior against Chief Delivery."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.prior_payroll_setup_helper import extract_unique_earnings_from_prior

PATH = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv"

df = pd.read_csv(PATH, dtype=str)
earnings = extract_unique_earnings_from_prior(df)
print(f"Found {len(earnings)} unique earning(s):\n")
print(f"  {'Type Code':<10s} Type Description")
print(f"  {'-' * 50}")
for r in earnings:
    print(f"  {r['Type Code']:<10s} {r['Type Description']}")
