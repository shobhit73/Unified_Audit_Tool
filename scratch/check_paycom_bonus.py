"""Sanity-check the Paycom-side Bonus totals straight from the CSV — no audit code."""
import pandas as pd
PAYCOM = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv'

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 250)

# Find header row dynamically (same logic as find_header_and_data_paycom)
df_peek = pd.read_csv(PAYCOM, header=None, nrows=20)
header_idx = 0
for i, row in df_peek.iterrows():
    row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
    if any(kw in row_str for kw in ["ee code", "description", "earning", "amount", "row labels"]):
        header_idx = i
        break

df = pd.read_csv(PAYCOM, header=header_idx)
print(f'Header row: {header_idx}, columns: {list(df.columns)[:15]}')

# Find desc and amt columns
desc_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["type description", "description", "earning/deduction/tax", "code description", "row labels"])), None)
amt_col = next((c for c in df.columns if "current amount" in str(c).lower()), None)
if not amt_col:
    amt_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["amount", "total amount", "value", "sum of amount"])), None)
print(f'desc_col={desc_col!r}, amt_col={amt_col!r}')

# Show ALL unique descriptions containing "bonus"
bonus_desc = df[df[desc_col].astype(str).str.contains('bonus', case=False, na=False)][desc_col].unique()
print(f'\nUnique descriptions containing "bonus": {list(bonus_desc)}')

# Sum by exact description
for d in bonus_desc:
    subset = df[df[desc_col].astype(str).str.strip().str.lower() == str(d).strip().lower()]
    s = pd.to_numeric(subset[amt_col], errors='coerce').sum()
    print(f'  {d!r}: rows={len(subset)}, sum={s:.2f}')

# Also examine Code Description distribution for Bonus rows
print('\nCode Description distribution for Bonus rows:')
code_col = next((c for c in df.columns if "code description" in str(c).lower()), None)
print(f'code_col={code_col!r}')
if code_col:
    bonus_rows = df[df[desc_col].astype(str).str.strip().str.lower() == 'bonus']
    print(bonus_rows[[desc_col, code_col, amt_col]].head(20).to_string())
    print('\nCode Description value counts on Bonus rows:')
    print(bonus_rows[code_col].value_counts(dropna=False).to_string())
