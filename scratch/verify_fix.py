import pandas as pd
import os
from utils.audit_utils import norm_colname

# Mocking clean_money_val from the real file
def clean_money_val(x):
    if pd.isna(x) or x == "":
        return 0.0
    s = str(x).strip()
    s_clean = s.replace("$", "").replace("%", "").replace(",", "")
    s_clean = s_clean.replace("(", "-").replace(")", "")
    try:
        return float(s_clean)
    except:
        return 0.0

def find_header_and_data(file):
    xls = pd.ExcelFile(file)
    target_sheet = xls.sheet_names[0]
    if len(xls.sheet_names) > 1 and "criteria" in xls.sheet_names[0].lower():
        target_sheet = xls.sheet_names[1]
    df_peek = pd.read_excel(xls, sheet_name=target_sheet, header=None, nrows=50)
    header_idx = 0
    for i, row in df_peek.iterrows():
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
        if "employee id" in row_str or "employee name" in row_str:
            header_idx = i
            break
    df = pd.read_excel(xls, sheet_name=target_sheet, header=header_idx)
    header_top = None
    if header_idx > 0:
        header_top = df_peek.iloc[header_idx - 1].tolist()
    return df, header_top, target_sheet

file_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior Payroll Register Report_2026-04-02-04-06-15.xlsx'
df, top, sheet = find_header_and_data(file_path)
print(f"Sheet used: {sheet}")
print(f"Top row match: {top[74] if top and len(top)>74 else 'None'}")
print(f"Main header match: {df.columns[74]}")

# Test summing for a specific column if possible
# Looking for 'NH STATE UNEMPLOYMENT TAX' in top or main
target = 'NH STATE UNEMPLOYMENT TAX'
found = False
if top:
    for i, val in enumerate(top):
        if str(val).lower() == target.lower():
            print(f"Found {target} in TOP row at column {i}")
            col_name = df.columns[i]
            total = df[col_name].apply(clean_money_val).sum()
            print(f"Total for {target}: {total}")
            found = True
            break
