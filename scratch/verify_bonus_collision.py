"""Verify the Bonus mismatch is caused by norm_colname() stripping parentheses,
which makes 'Bonus' and 'Bonus (Hours)' collide to the same normalized key 'bonus',
so the second column overwrites the first in norm_cols_main."""
import sys
sys.path.insert(0, r'c:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool')
import pandas as pd
from utils.audit_utils import norm_colname, clean_money_val

UZIO = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Prior Payroll Register Report_2026-06-01-05-38-22.xlsx'

xls = pd.ExcelFile(UZIO)
df_peek = pd.read_excel(xls, sheet_name='Prior Payroll Register', header=None, nrows=10)
df = pd.read_excel(xls, sheet_name='Prior Payroll Register', header=1)

# Reproduce the dict-build step from calculate_totals_uzio
norm_cols_main = {}
collisions = []
for i, c in enumerate(df.columns):
    key = norm_colname(c).lower()
    if key in norm_cols_main:
        collisions.append((key, df.columns[norm_cols_main[key]], i, c))
    norm_cols_main[key] = i

print(f"Total columns in UZIO main header: {len(df.columns)}")
print(f"Distinct normalized keys: {len(norm_cols_main)}")
print(f"\nCollisions (later column overwrites earlier):")
for k, old, new_idx, new_name in collisions:
    print(f"  key={k!r}: original={old!r} OVERWRITTEN by col {new_idx} {new_name!r}")

# What does the lookup for "Bonus" actually return?
print()
for ui in ['Bonus', 'Bonus (Hours)', 'Lookback bonus']:
    key = norm_colname(ui).lower()
    idx = norm_cols_main.get(key)
    resolved = df.columns[idx] if idx is not None else 'NOT FOUND'
    print(f"UZIO Item {ui!r} -> normalized {key!r} -> resolved column {resolved!r} (idx {idx})")

# Now show actual sums of the two bonus columns
print('\nActual sums (excluding total/grand rows):')
eid_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["employee id", "associate id"])), None)
work = df[df[eid_col].notna()].copy()
work[eid_col] = work[eid_col].astype(str).str.strip()
work = work[(work[eid_col] != "") & (~work[eid_col].str.lower().str.contains("total|grand", na=False))]

for col_idx in [13, 14, 16]:
    col_name = df.columns[col_idx]
    s = work.iloc[:, col_idx].apply(clean_money_val).sum()
    print(f"  col {col_idx} {col_name!r}: sum = {s:.2f}")
