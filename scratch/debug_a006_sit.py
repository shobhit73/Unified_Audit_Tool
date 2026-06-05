"""Trace exactly what happens for A006 in the new audit logic."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.withholding_audit import _pivot_uzio_long_to_wide

uzio = pd.read_csv(r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\Chief Delivery.csv", dtype=str)
fed, state = _pivot_uzio_long_to_wide(uzio)

print("--- federal_wide for A006 ---")
sub = fed[fed["employee_id"] == "A006"]
print(f"  Columns present: {sorted([c for c in sub.columns if sub[c].notna().any() and c.startswith('FIT_')])}")
print(f"  FIT_CHILD_AND_DEPENDENT_TAX_CREDIT: {sub['FIT_CHILD_AND_DEPENDENT_TAX_CREDIT'].iloc[0]!r}")
print(f"  FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD: {sub['FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD'].iloc[0]!r}")

print()
print("--- state_wide for A006 ---")
sub_s = state[state["employee_id"] == "A006"]
print(f"  Total state rows: {len(sub_s)}")
print(sub_s[["state_code"] + [c for c in sub_s.columns if c.startswith("SIT_")]].to_string(index=False))

print()
print("--- raw uzio rows for A006 with state_code populated ---")
raw = uzio[(uzio["employee_id"] == "A006") & uzio["state_code"].notna() & (uzio["state_code"] != "")]
print(raw[["state_code", "master_tax_type", "withholding_field_key", "withholding_field_value"]].to_string(index=False))
