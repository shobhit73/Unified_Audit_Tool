import pandas as pd
import os

file_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior Payroll Register Report_2026-04-02-04-06-15.xlsx'

if os.path.exists(file_path):
    print(f"File exists: {file_path}")
    xls = pd.ExcelFile(file_path)
    print(f"Sheet Names: {xls.sheet_names}")
    
    for sheet in xls.sheet_names:
        print(f"\n--- Checking Sheet: {sheet} ---")
        df_peek = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)
        print(df_peek.head(10))
else:
    print(f"File NOT found: {file_path}")
