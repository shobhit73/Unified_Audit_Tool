"""Verify Pre/Post-Tax classification on Chief Delivery deductions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.prior_payroll_setup_helper import (
    extract_unique_deductions_from_prior, bifurcate_match_memo,
    classify_pre_post_from_calc_description,
)

PATH = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv"

df = pd.read_csv(PATH, dtype=str)
all_deds = extract_unique_deductions_from_prior(df)
contribs, deds = bifurcate_match_memo(all_deds)
deds_with_verdict = classify_pre_post_from_calc_description(df, deds)

print(f"Deductions side after Pre/Post-Tax classification ({len(deds_with_verdict)} rows):\n")
print(f"  {'Type Code':<10s} {'Type Description':<26s} {'Calc Description':<40s} Pre/Post Tax")
print(f"  {'-' * 10:<10s} {'-' * 26:<26s} {'-' * 40:<40s} {'-' * 12}")
for r in deds_with_verdict:
    print(f"  {r['Type Code']:<10s} {r['Type Description']:<26s} {r['Calc Description']:<40s} {r['Pre/Post Tax']}")

# Summary
from collections import Counter
counts = Counter(r["Pre/Post Tax"] for r in deds_with_verdict)
print()
print(f"Tally: {dict(counts)}")
