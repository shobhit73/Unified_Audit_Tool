import pandas as pd
import os
from utils.audit_utils import norm_colname

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

def calculate_totals(df, header_top, column_names):
    total = 0.0
    found_cols = []
    mask = df.iloc[:, 0].astype(str).str.lower().str.contains("total|grand", na=False)
    df_clean = df[~mask].copy()
    norm_cols_top = {}
    if header_top:
        for i, c in enumerate(header_top):
            if pd.notna(c) and str(c).strip() != "":
                norm_cols_top[norm_colname(c).lower()] = i
    for name in column_names:
        n_name = norm_colname(name).lower()
        if n_name in norm_cols_top:
            start_idx = norm_cols_top[n_name]
            end_idx = len(df.columns)
            if header_top:
                for k in range(start_idx + 1, len(header_top)):
                    if pd.notna(header_top[k]) and str(header_top[k]).strip() != "":
                        end_idx = k
                        break
            for k in range(start_idx, end_idx):
                main_h = str(df.columns[k]).lower()
                if any(x in main_h for x in ['amount', 'total', 'current', 'ee', 'er', 'tax']):
                    if not any(x in main_h for x in ['wages', 'hours', 'rate', 'basis', 'taxable']):
                        total += df_clean.iloc[:, k].apply(clean_money_val).sum()
                        found_cols.append(f"{df.columns[k]}")
    return total, found_cols

file_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior Payroll Register Report_2026-04-02-04-06-15.xlsx'
df, top, sheet = find_header_and_data(file_path)
target = 'FEDERAL INCOME TAX' # Using a known tax from previous peek
tot, cols = calculate_totals(df, top, [target])
print(f"Target: {target}")
print(f"Columns Found: {cols}")
print(f"Total: {tot}")
