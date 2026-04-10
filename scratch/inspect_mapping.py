import pandas as pd
import os

file_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool\JM_Parcel_contribution_mapping.xlsx'

if os.path.exists(file_path):
    print(f"File exists at {file_path}")
    xls = pd.ExcelFile(file_path)
    print(f"Sheets: {xls.sheet_names}")
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, nrows=10)
        print(f"\n--- Sheet: {sheet} ---")
        print(df.head())
else:
    print(f"File NOT found at {file_path}")
