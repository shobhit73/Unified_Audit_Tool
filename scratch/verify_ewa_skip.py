"""Confirm EWA filter behaves: no-op on Chief Delivery (no EWA in file),
catches it when a synthetic EWA row is injected."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.prior_payroll_setup_helper import (
    extract_unique_deductions_from_prior, filter_default_uzio_deductions,
)

# Real Chief Delivery file
PATH = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv"
df = pd.read_csv(PATH, dtype=str)
all_deds = extract_unique_deductions_from_prior(df)
kept, skipped = filter_default_uzio_deductions(all_deds)
print(f"Chief Delivery: extracted={len(all_deds)}, kept={len(kept)}, skipped={len(skipped)}")
print(f"  Skipped rows: {skipped}")
print()

# Synthetic: inject an EWA row to prove the filter catches it
synthetic = pd.DataFrame([
    {"Code Description": "Deductions", "Type Code": "DEN", "Type Description": "Dental"},
    {"Code Description": "Deductions", "Type Code": "EWA", "Type Description": "Earned Wage Access"},
    {"Code Description": "Deductions", "Type Code": "EWA", "Type Description": "  EARNED WAGE ACCESS  "},  # case+ws
])
syn_extracted = extract_unique_deductions_from_prior(synthetic)
kept2, skipped2 = filter_default_uzio_deductions(syn_extracted)
print(f"Synthetic test (3 rows incl. 2 EWA variants):")
print(f"  extracted={len(syn_extracted)}, kept={len(kept2)}, skipped={len(skipped2)}")
print(f"  Kept: {kept2}")
print(f"  Skipped: {skipped2}")
